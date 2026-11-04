"""Pruebas unitarias e integración contra la especificación oficial de PTMP y pktctl."""
import json
import socket
import threading

import pytest

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTClient, protocol
from pt_mcp_bridge.ipc.protocol import Arg, FrameParser, Step
from pt_mcp_bridge.service import PacketTracerService


def test_frames_match_real_capture_and_pktctl():
    # 1. Trama real capturada de PT 9.0.1 sin argumentos
    call_no_args = b"46\x00100\x001725393348\x00appWindow\x000\x00isSimulationMode\x000\x00"
    assert protocol.call(1725393348, [Step("appWindow"), Step("isSimulationMode")]) == call_no_args

    # 2. Trama exacta del test oficial de pktctl (crates/ptmp/src/call.rs):
    #    network().getDevice(QString("R1")).getPort(String("GigabitEthernet0/0.10")).getIpAddress()
    #    Nota: NO hay contador de argumentos; cada método termina en "0" (END_OF_ARGUMENTS).
    steps = [
        Step("network"),
        Step("getDevice", (Arg.qstring("R1"),)),
        Step("getPort", (Arg.string("GigabitEthernet0/0.10"),)),
        Step("getIpAddress"),
    ]
    parsed = FrameParser().feed(protocol.call(4, steps))[0]
    assert parsed == [
        "100", "4",
        "network", "0",
        "getDevice", "9", "R1", "0",
        "getPort", "8", "GigabitEthernet0/0.10", "0",
        "getIpAddress", "0",
    ]

    # 3. Handshake y respuestas reales
    assert protocol.app_id("net.netacad.cisco.pt.ipctest") == b"31\x002\x00net.netacad.cisco.pt.ipctest\x00"
    assert protocol.auth("net.netacad.cisco.pt.ipctest", "cisco") == \
        b"38\x004\x00net.netacad.cisco.pt.ipctest\x00cisco\x00\x00"
    assert protocol.md5_digest("23k4SQ42tTFM6u4deW2jb1F2dZltz4t7", "probe-secret-123") == \
        "3417B8057B803EBC150BC7DABA451340"

    # 4. Pair response de Device.enterCommand: 14 (Pair), 4 (Int=0), 8 (String="output")
    pair_frame = ["102", "77", "14", "4", "0", "8", "Interface  IP-Address"]
    resp = protocol.parse_result(pair_frame)
    assert resp.request_id == 77 and resp.result == (0, "Interface  IP-Address")

    # 5. Error IPC tipo 101
    err_frame = ["101", "88", "Device", "IPC Cache entry:"]
    err_resp = protocol.parse_result(err_frame)
    assert err_resp.request_id == 88 and "Device: IPC Cache entry:" in err_resp.error


def test_add_device_and_create_link_wire_signatures():
    # addDevice(int type, string model, double x, double y)
    f_add = FrameParser().feed(protocol.call(1, calls.add_device(0, "2911", 100.0, 200.0)))[0]
    assert f_add == [
        "100", "1",
        "appWindow", "0",
        "getActiveWorkspace", "0",
        "getLogicalWorkspace", "0",
        "addDevice", "4", "0", "8", "2911", "7", "100.0", "7", "200.0", "0",
    ]

    # createLink(QString dev1, string port1, QString dev2, string port2, int ConnectType=8100)
    f_link = FrameParser().feed(
        protocol.call(2, calls.connect_ports("R1", "GigabitEthernet0/0", "S1", "FastEthernet0/1", 8100))
    )[0]
    assert f_link == [
        "100", "2",
        "appWindow", "0",
        "getActiveWorkspace", "0",
        "getLogicalWorkspace", "0",
        "createLink",
        "9", "R1",
        "8", "GigabitEthernet0/0",
        "9", "S1",
        "8", "FastEthernet0/1",
        "4", "8100",
        "0",
    ]


@pytest.fixture
def fake_pt():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    seen = []

    def serve():
        conn, _ = srv.accept()
        parser = FrameParser()
        while True:
            data = conn.recv(4096)
            if not data:
                return
            for f in parser.feed(data):
                seen.append(f)
                t = f[0]
                if t == protocol.HELLO:
                    conn.sendall(protocol.encode_frame(["1"] + f[1:]))
                elif t == protocol.APP_ID:
                    conn.sendall(protocol.encode_frame(["3", "X" * 32]))
                elif t == protocol.AUTH:
                    expected_md5 = protocol.md5_digest("X" * 32, "cisco")
                    ok = f[2] in ("cisco", expected_md5)
                    conn.sendall(protocol.encode_frame(["5", "true" if ok else "false"]))
                elif t == protocol.CALL:
                    rid = f[1]
                    if "addDevice" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "9", "Router0"]))
                    elif "createLink" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "2", "true"]))
                    elif "enterCommand" in f and "getCommandLine" not in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "14", "4", "0", "8", "OK"]))
                    elif "getDeviceCount" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "4", "1"]))
                    elif "getLinkCount" in f or "getType" in f or "getPortCount" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "4", "0"]))
                    elif "getCenterXCoordinate" in f or "getCenterYCoordinate" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "7", "150.0"]))
                    elif "getPrompt" in f:
                        conn.sendall(protocol.encode_frame(["102", rid, "8", "Router>"]))
                    else:
                        conn.sendall(protocol.encode_frame(["102", rid, "9", "R1"]))

    threading.Thread(target=serve, daemon=True).start()
    yield srv.getsockname()[1], seen
    srv.close()


def test_service_end_to_end(fake_pt):
    port, _seen = fake_pt
    c = PTClient()
    c.connect("127.0.0.1", port)
    svc = PacketTracerService(c)

    # 1. Agregar dispositivo (verifica addDevice + skipBoot + rename Router0 -> R1)
    added = json.loads(svc.add_device("R1", "router", "2911", 100, 200))
    assert added["name"] == "R1" and added["created_as"] == "Router0"

    # 2. Conectar puertos con auto-cable (usa código entero 8100/8101)
    link = json.loads(svc.connect_ports("R1", "GigabitEthernet0/0", "S1", "FastEthernet0/1", "straight"))
    assert link["code"] == 8100

    # 3. Enviar comandos CLI IOS (usa Device.enterCommand que devuelve Pair(status, output))
    cli_res = json.loads(svc.send_cli("R1", "show ip interface brief"))
    assert cli_res["status"] == "ok" and cli_res["output"] == "OK"

    # 4. Leer topología
    topo = json.loads(svc.topology())
    assert len(topo["devices"]) == 1 and topo["devices"][0]["name"] == "R1"

    # 5. Raw IPC con ipc_index.json
    raw = json.loads(svc.raw_ipc_call("network", [{"method": "getDevice", "args": ["R1"]}, {"method": "getName", "args": []}]))
    assert raw["result"] == "R1"

    c.disconnect()


def test_extended_tools_and_mcp_catalog(fake_pt):
    from pt_mcp_bridge.mcp_server import build_mcp

    port, _seen = fake_pt
    c = PTClient()
    c.connect("127.0.0.1", port)
    svc = PacketTracerService(c)

    # 1. Meta-herramientas sobre ipc_index.json (sin round-trip IPC)
    search_res = json.loads(svc.search_methods("addDevice", class_name="LogicalWorkspace"))
    assert search_res["count"] >= 1
    assert search_res["matches"][0]["method"] == "addDevice"

    desc_res = json.loads(svc.describe_method("LogicalWorkspace", "createLink"))
    assert desc_res["class"] == "LogicalWorkspace"
    assert len(desc_res["overloads"]) >= 1

    # 2. Operaciones L2 / L3 / Seguridad / Batch
    vlan_res = json.loads(svc.create_vlan("SW1", 10, "ADMIN"))
    assert vlan_res["completed"] is True

    ospf_res = json.loads(svc.configure_ospf("R1", 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.3", "area": 0}]))
    assert ospf_res["completed"] is True

    sec_res = json.loads(svc.secure_device("R1", "c1sc0", console_password="con", vty_password="vty"))
    assert sec_res["completed"] is True

    batch_res = json.loads(svc.batch([
        {"tool": "cpt_move_device", "args": {"name": "R1", "x": 250, "y": 250}},
        {"tool": "cpt_create_vlan", "args": {"device": "SW1", "vlan_id": 20, "name": "VOICE"}},
    ]))
    assert batch_res["executed"] == 2

    docs_res = json.loads(svc.generate_docs())
    assert "```mermaid" in docs_res["markdown"]

    # 3. Verificar que FastMCP registra todo el catálogo expandido (99 herramientas incluyendo redes móviles)
    mob_res = json.loads(svc.add_mobile_device("Celular1", "smartphone", "", 300, 300))
    assert mob_res["kind"] == "smartphone" and mob_res["model"] == "SMARTPHONE-PT"

    radio_res = json.loads(svc.configure_mobile_wifi_toggle("Celular1", "cellular"))
    assert radio_res["active_radio"] == "cellular"

    bt_res = json.loads(svc.configure_bluetooth("Celular1", enabled=True, discoverable=True))
    assert bt_res["bluetooth_enabled"] is True

    mcp = build_mcp(svc)
    registered_tools = list(mcp._tool_manager._tools.keys())
    assert len(registered_tools) >= 99
    for expected in (
        "cpt_move_device",
        "cpt_create_vlan",
        "cpt_configure_ospf",
        "cpt_configure_dhcp_server",
        "cpt_configure_acl",
        "cpt_configure_ssid",
        "cpt_traceroute",
        "cpt_check_activity",
        "cpt_search_methods",
        "cpt_describe_method",
        "cpt_batch",
        "cpt_run_macro",
        "cpt_add_mobile_device",
        "cpt_connect_cell_tower_to_co",
        "cpt_configure_cellular_interface",
        "cpt_configure_mobile_wifi_toggle",
        "cpt_deploy_cellular_topology",
        "cpt_simulate_mobile_handover",
        "cpt_set_mobile_velocity",
        "cpt_configure_bluetooth",
        "cpt_configure_ble_beacon",
        "cpt_audit_mobile_network",
    ):
        assert expected in registered_tools

    c.disconnect()

