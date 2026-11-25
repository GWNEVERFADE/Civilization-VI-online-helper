from __future__ import annotations

import ipaddress
import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from civ6_p2p.civ6_tunnel import ClientCiv6Bridge, HostCiv6Bridge
from civ6_p2p.easytier_manager import EasyTierSession, find_easytier_core, parse_easytier_peers
from civ6_p2p.network_utils import (
    STUN_ATTR_XOR_MAPPED_ADDRESS,
    STUN_BINDING_SUCCESS,
    STUN_MAGIC_COOKIE,
    build_stun_binding_request,
    canonicalize_ip,
    detect_local_network_info,
    format_endpoint,
    parse_stun_binding_response,
)
from civ6_p2p.p2p_node import P2PNode, PeerState, evaluate_step2_gate
from civ6_p2p.protocol import (
    MsgType,
    build_invite_code,
    compute_room_tag,
    pack_json_packet,
    pack_relay_forward,
    parse_peer_input,
    parse_server_address,
    unpack_json_payload,
    unpack_packet,
    unpack_relay_forward,
)
from civ6_p2p.relay_server import RelayServer
from civ6_p2p.win_civ6 import DISCOVERY_PAYLOAD


def _pick_free_udp_port(host: str = "127.0.0.1") -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestProtocolAndStun(unittest.TestCase):
    def test_invite_code_roundtrip_ipv6_and_ipv4(self) -> None:
        code6 = build_invite_code("240e:0000:0000::1234", 38666, nickname="房主A", role="host", room_key="mykey")
        self.assertTrue(code6.startswith("c6p2://[240e::1234]:38666?"))
        p6 = parse_peer_input(code6)
        self.assertEqual(p6.host, "240e::1234")
        self.assertEqual(p6.port, 38666)
        self.assertEqual(p6.ip_version, 6)
        self.assertEqual(p6.nickname, "房主A")
        self.assertEqual(p6.role, "host")
        self.assertEqual(p6.room_key, "mykey")

        p_raw6 = parse_peer_input("2408:8207::abcd", default_port=38666)
        self.assertEqual(p_raw6.host, "2408:8207::abcd")
        self.assertEqual(p_raw6.port, 38666)
        self.assertEqual(p_raw6.ip_version, 6)

        p4 = parse_peer_input("192.168.1.50:40000")
        self.assertEqual(p4.host, "192.168.1.50")
        self.assertEqual(p4.port, 40000)
        self.assertEqual(p4.ip_version, 4)

    def test_packet_pack_unpack(self) -> None:
        tag = compute_room_tag("secret")
        pkt = pack_json_packet(MsgType.HELLO, tag, {"nickname": "Test", "role": "host"})
        unpacked = unpack_packet(pkt)
        self.assertIsNotNone(unpacked)
        assert unpacked is not None
        mt, rtag, payload = unpacked
        self.assertEqual(mt, MsgType.HELLO)
        self.assertEqual(rtag, tag)
        self.assertEqual(unpack_json_payload(payload), {"nickname": "Test", "role": "host"})

    def test_stun_ipv6_and_ipv4_xor_mapped_parse(self) -> None:
        _, tx_id = build_stun_binding_request()

        target_v6 = ipaddress.IPv6Address("240e:1234::5678")
        target_port = 45678
        xport = target_port ^ (STUN_MAGIC_COOKIE >> 16)
        mask = struct.pack("!I", STUN_MAGIC_COOKIE) + tx_id
        xip = bytes(a ^ b for a, b in zip(target_v6.packed, mask))
        attr_val = struct.pack("!BBH", 0, 0x02, xport) + xip
        attr = struct.pack("!HH", STUN_ATTR_XOR_MAPPED_ADDRESS, len(attr_val)) + attr_val
        resp = struct.pack("!HHI12s", STUN_BINDING_SUCCESS, len(attr), STUN_MAGIC_COOKIE, tx_id) + attr

        parsed = parse_stun_binding_response(resp)
        self.assertEqual(parsed, (tx_id, "240e:1234::5678", 45678))

        target_v4 = ipaddress.IPv4Address("1.2.3.4")
        xport4 = 38666 ^ (STUN_MAGIC_COOKIE >> 16)
        xip4 = bytes(a ^ b for a, b in zip(target_v4.packed, struct.pack("!I", STUN_MAGIC_COOKIE)))
        attr_val4 = struct.pack("!BBH", 0, 0x01, xport4) + xip4
        attr4 = struct.pack("!HH", STUN_ATTR_XOR_MAPPED_ADDRESS, len(attr_val4)) + attr_val4
        resp4 = struct.pack("!HHI12s", STUN_BINDING_SUCCESS, len(attr4), STUN_MAGIC_COOKIE, tx_id) + attr4

        parsed4 = parse_stun_binding_response(resp4)
        self.assertEqual(parsed4, (tx_id, "1.2.3.4", 38666))

    def test_canonicalize_ipv4_mapped(self) -> None:
        self.assertEqual(canonicalize_ip("::ffff:10.0.0.1"), ("10.0.0.1", 4))
        self.assertEqual(format_endpoint("::ffff:10.0.0.1", 38666), "10.0.0.1:38666")
        self.assertEqual(format_endpoint("240e:0000::1", 38666), "[240e::1]:38666")


class TestIPv6P2PAndCiv6Bridge(unittest.TestCase):
    def test_ipv6_p2p_connect_status_test_and_bye(self) -> None:
        host_status = {"running": True, "room_ready": True, "session_ready": True}
        client_status = {"running": True, "room_ready": False, "session_ready": False}

        host = P2PNode(
            nickname="HostPC",
            role="host",
            listen_port=0,
            room_key="room42",
            local_civ6_status_fn=lambda: host_status,
        )
        client = P2PNode(
            nickname="ClientPC",
            role="client",
            listen_port=0,
            room_key="room42",
            local_civ6_status_fn=lambda: client_status,
        )
        try:
            h_port = host.start()
            c_port = client.start()
            self.assertTrue(host.is_ipv6_socket)
            self.assertTrue(client.is_ipv6_socket)

            peer = client.add_peer("::1", h_port, nickname="HostPC", role="host")
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                cp = client.get_peer(peer.peer_key)
                hp_list = host.list_peers()
                if cp and cp.status == "online" and hp_list and hp_list[0].status == "online":
                    break
                time.sleep(0.05)

            cp = client.get_peer(peer.peer_key)
            self.assertIsNotNone(cp)
            assert cp is not None
            self.assertEqual(cp.status, "online")
            self.assertEqual(cp.nickname, "HostPC")
            self.assertTrue(cp.remote_civ6_running)
            self.assertTrue(cp.remote_civ6_room_ready)

            res = client.run_connectivity_test(peer.peer_key, count=5, timeout_s=2.0)
            self.assertTrue(res.passed, f"Test failed: {res.summary}")
            self.assertEqual(res.received, 5)
            self.assertTrue(res.large_pkt_ok)
            self.assertIsNotNone(res.avg_rtt_ms)

            cp_after = client.get_peer(peer.peer_key)
            assert cp_after is not None
            self.assertTrue(cp_after.verified)

            host.stop()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                cp_off = client.get_peer(peer.peer_key)
                if cp_off and cp_off.status == "offline":
                    break
                time.sleep(0.05)
            cp_off = client.get_peer(peer.peer_key)
            assert cp_off is not None
            self.assertEqual(cp_off.status, "offline")
        finally:
            client.stop()
            host.stop()

    def test_room_key_mismatch_rejected(self) -> None:
        host = P2PNode(nickname="H", role="host", listen_port=0, room_key="keyA")
        client = P2PNode(nickname="C", role="client", listen_port=0, room_key="keyB")
        try:
            h_port = host.start()
            client.start()
            peer = client.add_peer("::1", h_port)
            time.sleep(0.6)
            cp = client.get_peer(peer.peer_key)
            assert cp is not None
            self.assertEqual(cp.status, "connecting")
            self.assertEqual(len(host.list_peers()), 0)
        finally:
            client.stop()
            host.stop()

    def test_full_civ6_discovery_and_session_over_ipv6_p2p(self) -> None:
        sim_host_disc_port = _pick_free_udp_port()
        sim_host_sess_port = _pick_free_udp_port()
        sim_client_fake_disc_port = _pick_free_udp_port()
        sim_client_fake_sess_port = _pick_free_udp_port()

        stop_sim = threading.Event()
        fake_room_pkt_1 = b"CIV6_ROOM_JSON_PART_1:" + (b"R" * 1082)
        fake_room_pkt_2 = b"CIV6_ROOM_JSON_PART_2:" + (b"S" * 500)
        host_sess_seen_from: list[tuple[str, int]] = []

        sim_host_disc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_disc.bind(("127.0.0.1", sim_host_disc_port))
        sim_host_disc.settimeout(0.1)

        sim_host_sess = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_sess.bind(("127.0.0.1", sim_host_sess_port))
        sim_host_sess.settimeout(0.1)

        def sim_host_loop() -> None:
            while not stop_sim.is_set():
                try:
                    data, addr = sim_host_disc.recvfrom(4096)
                    if data == DISCOVERY_PAYLOAD:
                        sim_host_disc.sendto(fake_room_pkt_1, addr)
                        sim_host_disc.sendto(fake_room_pkt_2, addr)
                except socket.timeout:
                    pass
                except OSError:
                    break

                try:
                    sdata, saddr = sim_host_sess.recvfrom(4096)
                    host_sess_seen_from.append(saddr)
                    sim_host_sess.sendto(b"HOST_ACK:" + sdata, saddr)
                except socket.timeout:
                    pass
                except OSError:
                    break

        sim_thread = threading.Thread(target=sim_host_loop, daemon=True)
        sim_thread.start()

        host_node = P2PNode(nickname="Host", role="host", listen_port=0, room_key="civ6test")
        client_node = P2PNode(nickname="Client", role="client", listen_port=0, room_key="civ6test")
        host_bridge = None
        client_bridge = None
        sim_client_ephem = None
        sim_client_sess = None

        try:
            h_port = host_node.start()
            client_node.start()
            peer = client_node.add_peer("::1", h_port, nickname="Host", role="host")

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                cp = client_node.get_peer(peer.peer_key)
                if cp and cp.status == "online" and host_node.list_peers():
                    break
                time.sleep(0.05)

            test_res = client_node.run_connectivity_test(peer.peer_key, count=5, timeout_s=2.0)
            self.assertTrue(test_res.passed)

            host_bridge = HostCiv6Bridge(
                host_node,
                target_host_ip="127.0.0.1",
                target_disc_port=sim_host_disc_port,
                target_session_port=sim_host_sess_port,
                local_session_bind_port=sim_host_sess_port,
            )
            host_bridge.start()

            client_bridge = ClientCiv6Bridge(
                client_node,
                host_peer_key=peer.peer_key,
                fake_host_ip="127.0.127.5",
                local_disc_port=sim_client_fake_disc_port,
                local_session_port=sim_client_fake_sess_port,
                enable_windows_watcher=False,
                enable_broadcast_sniffer=False,
            )
            client_bridge.start()

            ok, pkt_cnt, total_bytes = client_bridge.probe_host_room(timeout_s=2.0)
            self.assertTrue(ok)
            self.assertEqual(pkt_cnt, 2)
            self.assertEqual(total_bytes, len(fake_room_pkt_1) + len(fake_room_pkt_2))

            sim_client_ephem = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sim_client_ephem.bind(("0.0.0.0", 0))
            ephem_port = sim_client_ephem.getsockname()[1]
            sim_client_ephem.settimeout(2.0)

            client_bridge.trigger_discovery_for_port(ephem_port, DISCOVERY_PAYLOAD, source="test")
            got_pkts = []
            for _ in range(2):
                d, a = sim_client_ephem.recvfrom(4096)
                got_pkts.append((d, a))
            self.assertEqual(got_pkts[0][0], fake_room_pkt_1)
            self.assertEqual(got_pkts[0][1], ("127.0.127.5", sim_client_fake_disc_port))
            self.assertEqual(got_pkts[1][0], fake_room_pkt_2)

            sim_client_sess = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sim_client_sess.bind(("0.0.0.0", 0))
            sim_client_sess.settimeout(2.0)

            join_pkt = b"RAKNET_JOIN_HELLO_" + (b"J" * 102)
            sim_client_sess.sendto(join_pkt, ("127.0.127.5", sim_client_fake_sess_port))
            reply, reply_addr = sim_client_sess.recvfrom(4096)
            self.assertEqual(reply, b"HOST_ACK:" + join_pkt)
            self.assertEqual(reply_addr, ("127.0.127.5", sim_client_fake_sess_port))
            self.assertTrue(host_sess_seen_from)
            self.assertTrue(host_sess_seen_from[0][0].startswith("127.0.127."))
            self.assertEqual(host_sess_seen_from[0][1], sim_host_sess_port)

            c_stats = client_bridge.get_stats()
            h_stats = host_bridge.get_stats()
            self.assertGreaterEqual(c_stats.disc_resps, 2)
            self.assertEqual(c_stats.session_tx_pkts, 1)
            self.assertEqual(c_stats.session_rx_pkts, 1)
            self.assertEqual(h_stats.session_rx_pkts, 1)
            self.assertEqual(h_stats.session_tx_pkts, 1)
        finally:
            stop_sim.set()
            if client_bridge:
                client_bridge.stop()
            if host_bridge:
                host_bridge.stop()
            client_node.stop()
            host_node.stop()
            for s in (sim_host_disc, sim_host_sess, sim_client_ephem, sim_client_sess):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            sim_thread.join(timeout=1.0)


class TestServerRelayMode(unittest.TestCase):
    def test_relay_protocol_and_server_addr_parse(self) -> None:
        self.assertEqual(parse_server_address("relay.example.com:38668"), ("relay.example.com", 38668))
        self.assertEqual(parse_server_address("relay.example.com"), ("relay.example.com", 38668))
        self.assertEqual(parse_server_address("[240e::1]:40000"), ("240e::1", 40000))
        self.assertEqual(parse_server_address("1.2.3.4"), ("1.2.3.4", 38668))

        tag = compute_room_tag("pw")
        pkt = pack_relay_forward(tag, "room1", "nodeA", "nodeB", b"INNER_PAYLOAD")
        unpacked = unpack_packet(pkt)
        assert unpacked is not None
        self.assertEqual(unpacked[0], MsgType.RELAY_FORWARD)
        self.assertEqual(unpack_relay_forward(unpacked[2]), ("room1", "nodeA", "nodeB", b"INNER_PAYLOAD"))

    def test_relay_auto_discovery_room_isolation_and_test(self) -> None:
        relay = RelayServer(listen_port=0, idle_timeout_s=10.0)
        host = P2PNode(
            nickname="RelayHost",
            role="host",
            listen_port=0,
            room_key="team1",
            local_civ6_status_fn=lambda: {"running": True, "room_ready": True, "session_ready": True},
        )
        client = P2PNode(nickname="RelayClient", role="client", listen_port=0, room_key="team1")
        stranger = P2PNode(nickname="Stranger", role="client", listen_port=0, room_key="other_key")

        try:
            rport = relay.start()
            host.start()
            client.start()
            stranger.start()

            host.connect_relay(f"[::1]:{rport}", "civ-room-a")
            client.connect_relay(f"127.0.0.1:{rport}", "civ-room-a")
            stranger.connect_relay(f"127.0.0.1:{rport}", "civ-room-a")

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                c_peers = client.list_peers()
                h_peers = host.list_peers()
                if (
                    c_peers
                    and c_peers[0].status == "online"
                    and h_peers
                    and h_peers[0].status == "online"
                ):
                    break
                time.sleep(0.05)

            c_peers = client.list_peers()
            h_peers = host.list_peers()
            self.assertEqual(len(c_peers), 1)
            self.assertEqual(len(h_peers), 1)
            self.assertEqual(len(stranger.list_peers()), 0)

            hp = c_peers[0]
            self.assertEqual(hp.transport, "relay")
            self.assertEqual(hp.transport_label(), "EasyTier 中继")
            self.assertEqual(hp.nickname, "RelayHost")
            self.assertEqual(hp.status, "online")
            self.assertTrue(hp.remote_civ6_room_ready)

            res = client.run_connectivity_test(hp.peer_key, count=5, timeout_s=2.0)
            self.assertTrue(res.passed, f"Relay test failed: {res.summary}")
            self.assertEqual(res.received, 5)
            self.assertTrue(res.large_pkt_ok)

            host.disconnect_relay()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                p_after = client.get_peer(hp.peer_key)
                if p_after and p_after.status == "offline":
                    break
                time.sleep(0.05)
            p_after = client.get_peer(hp.peer_key)
            assert p_after is not None
            self.assertEqual(p_after.status, "offline")
        finally:
            stranger.stop()
            client.stop()
            host.stop()
            relay.stop()

    def test_full_civ6_discovery_and_session_over_relay_server(self) -> None:
        sim_host_disc_port = _pick_free_udp_port()
        sim_host_sess_port = _pick_free_udp_port()
        sim_client_fake_disc_port = _pick_free_udp_port()
        sim_client_fake_sess_port = _pick_free_udp_port()

        stop_sim = threading.Event()
        fake_room_pkt = b"RELAY_CIV6_ROOM:" + (b"Z" * 1088)

        sim_host_disc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_disc.bind(("127.0.0.1", sim_host_disc_port))
        sim_host_disc.settimeout(0.1)

        sim_host_sess = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_sess.bind(("127.0.0.1", sim_host_sess_port))
        sim_host_sess.settimeout(0.1)

        def sim_host_loop() -> None:
            while not stop_sim.is_set():
                try:
                    data, addr = sim_host_disc.recvfrom(4096)
                    if data == DISCOVERY_PAYLOAD:
                        sim_host_disc.sendto(fake_room_pkt, addr)
                except socket.timeout:
                    pass
                except OSError:
                    break

                try:
                    sdata, saddr = sim_host_sess.recvfrom(4096)
                    sim_host_sess.sendto(b"RELAY_HOST_OK:" + sdata, saddr)
                except socket.timeout:
                    pass
                except OSError:
                    break

        sim_thread = threading.Thread(target=sim_host_loop, daemon=True)
        sim_thread.start()

        relay = RelayServer(listen_port=0)
        host_node = P2PNode(nickname="Host", role="host", listen_port=0, room_key="rkey")
        client_node = P2PNode(nickname="Client", role="client", listen_port=0, room_key="rkey")
        host_bridge = None
        client_bridge = None
        sim_client_ephem = None
        sim_client_sess = None

        try:
            rport = relay.start()
            host_node.start()
            client_node.start()

            host_node.connect_relay(f"[::1]:{rport}", "game99")
            client_node.connect_relay(f"127.0.0.1:{rport}", "game99")

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                cp = client_node.list_peers()
                hp = host_node.list_peers()
                if cp and cp[0].status == "online" and hp and hp[0].status == "online":
                    break
                time.sleep(0.05)

            host_peer = client_node.list_peers()[0]
            self.assertEqual(host_peer.transport, "relay")

            host_bridge = HostCiv6Bridge(
                host_node,
                target_host_ip="127.0.0.1",
                target_disc_port=sim_host_disc_port,
                target_session_port=sim_host_sess_port,
                local_session_bind_port=sim_host_sess_port,
            )
            host_bridge.start()

            client_bridge = ClientCiv6Bridge(
                client_node,
                host_peer_key=host_peer.peer_key,
                fake_host_ip="127.0.127.9",
                local_disc_port=sim_client_fake_disc_port,
                local_session_port=sim_client_fake_sess_port,
                enable_windows_watcher=False,
                enable_broadcast_sniffer=False,
            )
            client_bridge.start()

            ok, cnt, total_b = client_bridge.probe_host_room(timeout_s=2.0)
            self.assertTrue(ok)
            self.assertEqual(cnt, 1)
            self.assertEqual(total_b, len(fake_room_pkt))

            sim_client_ephem = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sim_client_ephem.bind(("0.0.0.0", 0))
            ephem_port = sim_client_ephem.getsockname()[1]
            sim_client_ephem.settimeout(2.0)

            client_bridge.trigger_discovery_for_port(ephem_port, DISCOVERY_PAYLOAD, source="relay-test")
            got_room, got_addr = sim_client_ephem.recvfrom(4096)
            self.assertEqual(got_room, fake_room_pkt)
            self.assertEqual(got_addr, ("127.0.127.9", sim_client_fake_disc_port))

            sim_client_sess = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sim_client_sess.bind(("0.0.0.0", 0))
            sim_client_sess.settimeout(2.0)

            join_pkt = b"CIV6_JOIN_VIA_RELAY_" + (b"X" * 100)
            sim_client_sess.sendto(join_pkt, ("127.0.127.9", sim_client_fake_sess_port))
            reply, raddr = sim_client_sess.recvfrom(4096)
            self.assertEqual(reply, b"RELAY_HOST_OK:" + join_pkt)
            self.assertEqual(raddr, ("127.0.127.9", sim_client_fake_sess_port))

            st = relay.get_stats()
            self.assertGreater(st.fwd_packets, 0)
            self.assertGreater(st.fwd_bytes, len(fake_room_pkt))
        finally:
            stop_sim.set()
            if client_bridge:
                client_bridge.stop()
            if host_bridge:
                host_bridge.stop()
            client_node.stop()
            host_node.stop()
            relay.stop()
            for s in (sim_host_disc, sim_host_sess, sim_client_ephem, sim_client_sess):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            sim_thread.join(timeout=1.0)


class TestStep2GatePolicy(unittest.TestCase):
    def test_gate_requires_running_and_two_online_and_verified(self) -> None:
        g0 = evaluate_step2_gate(False, [])
        self.assertEqual(g0.total_online, 0)
        self.assertFalse(g0.can_enter_step2)

        g1 = evaluate_step2_gate(True, [])
        self.assertEqual(g1.total_online, 1)
        self.assertFalse(g1.can_enter_step2)

        p_conn = PeerState(peer_key="[::1]:38666", host="::1", port=38666, ip_version=6, fake_ip="127.0.127.1", status="connecting", verified=True)
        g_conn = evaluate_step2_gate(True, [p_conn])
        self.assertEqual(g_conn.total_online, 1)
        self.assertFalse(g_conn.can_enter_step2)

        p_unverified = PeerState(peer_key="[::1]:38666", host="::1", port=38666, ip_version=6, fake_ip="127.0.127.1", status="online", verified=False)
        g_unver = evaluate_step2_gate(True, [p_unverified])
        self.assertEqual(g_unver.total_online, 2)
        self.assertFalse(g_unver.can_enter_step2)

        p_ok = PeerState(peer_key="[::1]:38666", host="::1", port=38666, ip_version=6, fake_ip="127.0.127.1", status="online", verified=True, nickname="HostA")
        g_ok = evaluate_step2_gate(True, [p_ok])
        self.assertEqual(g_ok.total_online, 2)
        self.assertTrue(g_ok.can_enter_step2)
        self.assertEqual(p_ok.transport_label(), "IPv6/P2P 直连")

        p_off = PeerState(peer_key="[::1]:38666", host="::1", port=38666, ip_version=6, fake_ip="127.0.127.1", status="offline", verified=True)
        g_off = evaluate_step2_gate(True, [p_off])
        self.assertEqual(g_off.total_online, 1)
        self.assertFalse(g_off.can_enter_step2)

    def test_gui_has_two_tabs_and_locks_step2_until_verified(self) -> None:
        from civ6_p2p.gui import Civ6P2PApp

        app = Civ6P2PApp()
        try:
            app.update()
            self.assertEqual(len(app.notebook.tabs()), 2)
            self.assertEqual(str(app.notebook.tab(app.tab_step2, "state")), "disabled")
            self.assertEqual(str(app.goto_step2_btn["state"]), "disabled")
            self.assertEqual(str(app.start_bridge_btn["state"]), "disabled")

            p_ok = PeerState(
                peer_key="[::1]:38666",
                host="::1",
                port=38666,
                ip_version=6,
                fake_ip="127.0.127.1",
                role="host",
                nickname="HostA",
                status="online",
                verified=True,
            )
            app._sync_target_host_combo([p_ok])
            app._apply_step2_gate(evaluate_step2_gate(True, [p_ok]))
            self.assertEqual(str(app.notebook.tab(app.tab_step2, "state")), "normal")
            self.assertEqual(str(app.goto_step2_btn["state"]), "normal")
            self.assertEqual(str(app.start_bridge_btn["state"]), "normal")

            p_off = p_ok.copy_snapshot()
            p_off.status = "offline"
            app._sync_target_host_combo([p_off])
            app._apply_step2_gate(evaluate_step2_gate(True, [p_off]))
            self.assertEqual(str(app.notebook.tab(app.tab_step2, "state")), "disabled")
            self.assertEqual(str(app.start_bridge_btn["state"]), "disabled")
        finally:
            app._on_close()


class TestEasyTierEmbeddedIntegration(unittest.TestCase):
    def test_no_public_presets_bundled(self) -> None:
        from civ6_p2p.easytier_manager import DEFAULT_EASYTIER_NODE_PRESETS

        self.assertEqual(DEFAULT_EASYTIER_NODE_PRESETS, [])

    def test_parse_easytier_peers(self) -> None:
        self.assertEqual(
            parse_easytier_peers("tcp://my-vps.example.com:11010  [香港自建 VPS]"),
            ["tcp://my-vps.example.com:11010"],
        )
        self.assertEqual(
            parse_easytier_peers("tcp://a.com:11010, b.com:11010"),
            ["tcp://a.com:11010", "tcp://b.com:11010"],
        )

    def test_live_easytier_no_tun_host_client_and_civ6_traffic(self) -> None:
        exe = find_easytier_core()
        self.assertTrue(exe.is_file())

        lan_ip = detect_local_network_info().default_ipv4
        if not lan_ip:
            self.skipTest("No non-loopback IPv4 available for local EasyTier peer test")

        et_listen_port = _pick_free_udp_port()
        host_relay_port = _pick_free_udp_port()

        host_et = EasyTierSession(
            role="host",
            room_name="civ6-et-e2e",
            room_secret="et-secret-123",
            peer_uris=[],
            hostname="et-host",
            host_relay_port=host_relay_port,
            extra_listeners=[f"tcp://{lan_ip}:{et_listen_port}"],
        )
        client_et = EasyTierSession(
            role="client",
            room_name="civ6-et-e2e",
            room_secret="et-secret-123",
            peer_uris=[f"tcp://{lan_ip}:{et_listen_port}"],
            hostname="et-client",
            host_relay_port=host_relay_port,
        )
        host_node = P2PNode(nickname="ET_Host", role="host", listen_port=0, room_key="et-secret-123")
        client_node = P2PNode(nickname="ET_Client", role="client", listen_port=0, room_key="et-secret-123")

        try:
            h_addr = host_et.start()
            c_addr = client_et.start()
            host_node.start()
            client_node.start()

            host_node.connect_relay(h_addr, "civ6-et-e2e", transport_name="EasyTier 中继")
            client_node.connect_relay(c_addr, "civ6-et-e2e", transport_name="EasyTier 中继")

            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                cp = client_node.list_peers()
                hp = host_node.list_peers()
                if cp and cp[0].status == "online" and hp and hp[0].status == "online":
                    break
                time.sleep(0.15)

            cp = client_node.list_peers()
            hp = host_node.list_peers()
            self.assertEqual(len(cp), 1)
            self.assertEqual(len(hp), 1)
            self.assertEqual(cp[0].status, "online")
            self.assertEqual(cp[0].transport_label(), "EasyTier 中继")

            res = client_node.run_connectivity_test(cp[0].peer_key, count=5, timeout_s=3.0)
            self.assertTrue(res.passed, f"EasyTier connectivity test failed: {res.summary}")
            self.assertTrue(res.large_pkt_ok)
        finally:
            client_node.stop()
            host_node.stop()
            client_et.stop()
            host_et.stop()

    def test_live_easytier_midgame_disconnect_rejoin_and_civ6_traffic(self) -> None:
        import subprocess
        import uuid

        exe = find_easytier_core()
        self.assertTrue(exe.is_file())
        lan_ip = detect_local_network_info().default_ipv4
        if not lan_ip:
            self.skipTest("No non-loopback IPv4 available for live EasyTier VPS rejoin test")

        vps_port = _pick_free_udp_port()
        host_relay_port = _pick_free_udp_port()
        sim_host_disc_port = _pick_free_udp_port()
        sim_host_sess_port = _pick_free_udp_port()

        stop_sim = threading.Event()
        fake_room_pkt = b"MIDGAME_CIV6_ROOM:" + (b"M" * 1086)
        sim_host_disc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_disc.bind(("127.0.0.1", sim_host_disc_port))
        sim_host_disc.settimeout(0.1)
        sim_host_sess = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sim_host_sess.bind(("127.0.0.1", sim_host_sess_port))
        sim_host_sess.settimeout(0.1)

        def sim_host_loop() -> None:
            while not stop_sim.is_set():
                try:
                    data, addr = sim_host_disc.recvfrom(4096)
                    if data == DISCOVERY_PAYLOAD:
                        sim_host_disc.sendto(fake_room_pkt, addr)
                except (socket.timeout, OSError):
                    pass
                try:
                    sdata, saddr = sim_host_sess.recvfrom(4096)
                    sim_host_sess.sendto(b"GAME_ACK:" + sdata, saddr)
                except (socket.timeout, OSError):
                    pass

        sim_thread = threading.Thread(target=sim_host_loop, daemon=True)
        sim_thread.start()

        vps_proc = subprocess.Popen(
            [
                str(exe),
                "--no-tun",
                "--machine-id",
                str(uuid.uuid4()),
                "-l",
                f"tcp://{lan_ip}:{vps_port}",
                "-l",
                f"udp://{lan_ip}:{vps_port}",
                "-r",
                "0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)

        host_et = EasyTierSession(
            role="host",
            room_name="civ6-midgame",
            room_secret="mid-sec",
            peer_uris=[f"tcp://{lan_ip}:{vps_port}"],
            hostname="HostPC",
            host_relay_port=host_relay_port,
        )
        host_node = P2PNode(nickname="HostPC", role="host", listen_port=0, room_key="mid-sec")
        host_bridge = None
        active_clients: list[tuple[EasyTierSession, P2PNode, ClientCiv6Bridge]] = []

        def join_and_play(nick: str, tag: bytes) -> tuple[EasyTierSession, P2PNode, ClientCiv6Bridge]:
            cet = EasyTierSession(
                role="client",
                room_name="civ6-midgame",
                room_secret="mid-sec",
                peer_uris=[f"tcp://{lan_ip}:{vps_port}"],
                hostname=nick,
                host_relay_port=host_relay_port,
            )
            cn = P2PNode(nickname=nick, role="client", listen_port=0, room_key="mid-sec")
            caddr = cet.start()
            cn.start()
            cn.connect_relay(caddr, "civ6-midgame", transport_name="VPS EasyTier")

            deadline = time.monotonic() + 10.0
            host_peer = None
            while time.monotonic() < deadline:
                for p in cn.list_peers():
                    if p.role == "host" and p.status == "online":
                        host_peer = p
                        break
                if host_peer is not None:
                    break
                time.sleep(0.15)
            self.assertIsNotNone(host_peer, f"{nick} failed to see online Host via VPS EasyTier")
            assert host_peer is not None

            res = cn.run_connectivity_test(host_peer.peer_key, count=5, timeout_s=3.0)
            self.assertTrue(res.passed, f"{nick} connectivity test failed: {res.summary}")

            fake_disc_p = _pick_free_udp_port()
            fake_sess_p = _pick_free_udp_port()
            cb = ClientCiv6Bridge(
                cn,
                host_peer_key=host_peer.peer_key,
                fake_host_ip="127.0.127.55" if nick == "PlayerA" else "127.0.127.56",
                local_disc_port=fake_disc_p,
                local_session_port=fake_sess_p,
                enable_windows_watcher=False,
                enable_broadcast_sniffer=False,
            )
            cb.start()

            ok, cnt, _ = cb.probe_host_room(timeout_s=2.0)
            self.assertTrue(ok, f"{nick} failed to probe ongoing Civ6 room")
            self.assertEqual(cnt, 1)

            sim_cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sim_cli.bind(("0.0.0.0", 0))
                sim_cli.settimeout(2.0)
                sim_cli.sendto(tag, (cb.fake_host_ip, fake_sess_p))
                reply, _ = sim_cli.recvfrom(4096)
                self.assertEqual(reply, b"GAME_ACK:" + tag)
            finally:
                sim_cli.close()

            return cet, cn, cb

        try:
            haddr = host_et.start()
            host_node.start()
            host_node.connect_relay(haddr, "civ6-midgame", transport_name="VPS EasyTier")
            host_bridge = HostCiv6Bridge(
                host_node,
                target_host_ip="127.0.0.1",
                target_disc_port=sim_host_disc_port,
                target_session_port=sim_host_sess_port,
                local_session_bind_port=sim_host_sess_port,
            )
            host_bridge.start()
            time.sleep(1.0)

            a1_et, a1_n, a1_cb = join_and_play("PlayerA", b"PLAYER_A_ROUND_1")

            a1_cb.stop()
            a1_n.stop()
            a1_et.stop()

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if len(host_bridge._peer_sess_socks) == 0:
                    break
                time.sleep(0.1)
            self.assertEqual(len(host_bridge._peer_sess_socks), 0, "HostCiv6Bridge leaked stale session socket")

            a2 = join_and_play("PlayerA", b"PLAYER_A_REJOIN_MIDGAME")
            active_clients.append(a2)

            host_peers_after = [p for p in host_node.list_peers() if p.nickname == "PlayerA"]
            self.assertEqual(len(host_peers_after), 1)
            self.assertEqual(host_peers_after[0].status, "online")

            b1 = join_and_play("PlayerB", b"PLAYER_B_HOTJOIN_MIDGAME")
            active_clients.append(b1)
        finally:
            stop_sim.set()
            for cet, cn, cb in active_clients:
                cb.stop()
                cn.stop()
                cet.stop()
            if host_bridge is not None:
                host_bridge.stop()
            host_node.stop()
            host_et.stop()
            vps_proc.terminate()
            try:
                vps_proc.wait(timeout=2.0)
            except Exception:
                vps_proc.kill()
            sim_host_disc.close()
            sim_host_sess.close()
            sim_thread.join(timeout=1.0)


class TestGlassGuiController(unittest.TestCase):
    def test_glass_html_assets_inline_cleanly(self) -> None:
        from civ6_p2p.glass_gui import load_glass_html

        html = load_glass_html()
        self.assertIn("CV6 online helper", html)
        self.assertNotIn("__INLINE_CSS__", html)
        self.assertNotIn("__INLINE_JS__", html)
        self.assertNotIn("__APP_LOGO_DATA_URI__", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("backdrop-filter", html)
        self.assertIn("hyperLightBloom", html)
        self.assertIn("lang-toggle", html)

    def test_glass_controller_bilingual_lang_switch_and_persistence(self) -> None:
        import tempfile
        from civ6_p2p.glass_gui import GlassAppController
        from civ6_p2p.vps_store import UiPrefsStore

        with tempfile.TemporaryDirectory() as tmpdir:
            vps_file = Path(tmpdir) / "vps.json"
            prefs_file = Path(tmpdir) / "ui_prefs.json"
            ctrl = GlassAppController(start_bg_poller=False, vps_store_path=vps_file, prefs_path=prefs_file)
            try:
                st_zh = ctrl.get_state()
                self.assertEqual(st_zh["lang"], "zh")
                self.assertIn("未启动", st_zh["step2"]["bridge_status"])

                res_en = ctrl.set_lang("en")
                self.assertTrue(res_en["ok"])
                self.assertEqual(res_en["lang"], "en")

                st_en = ctrl.get_state()
                self.assertEqual(st_en["lang"], "en")
                self.assertEqual(st_en["step2"]["bridge_status"], "Not Started")
                self.assertIn("Start your local node first", st_en["gate"]["reason"])
                self.assertIn("Not Running", st_en["civ6_summary"])

                reloaded = UiPrefsStore(path=prefs_file)
                self.assertEqual(reloaded.lang, "en")

                ctrl2 = GlassAppController(start_bg_poller=False, vps_store_path=vps_file, prefs_path=prefs_file)
                try:
                    self.assertEqual(ctrl2.get_state()["lang"], "en")
                    ctrl2.set_lang("zh")
                    self.assertEqual(ctrl2.get_state()["lang"], "zh")
                finally:
                    ctrl2.shutdown()
            finally:
                ctrl.shutdown()

    def test_glass_controller_two_step_gate_and_p2p_flow(self) -> None:
        import tempfile
        from civ6_p2p.glass_gui import GlassAppController

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GlassAppController(start_bg_poller=False, vps_store_path=Path(tmpdir) / "vps.json")
            remote_host = P2PNode(nickname="RemoteHost", role="host", listen_port=0, room_key="glass-room")
            try:
                st0 = ctrl.get_state()
                self.assertFalse(st0["node_running"])
                self.assertEqual(st0["vps_nodes"], [])
                self.assertEqual(st0["et_node"], "")
                self.assertFalse(st0["gate"]["can_enter_step2"])
                self.assertFalse(st0["step2"]["can_start_bridge"])

                h_port = remote_host.start()
                res = ctrl.start_node(role="client", nickname="GlassClient", port_text="0", room_key="glass-room")
                self.assertTrue(res["ok"])

                add_res = ctrl.add_peer(f"[::1]:{h_port}")
                self.assertTrue(add_res["ok"])
                peer_key = add_res["peer_key"]

                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    st = ctrl.get_state()
                    if st["peers"] and st["peers"][0]["status"] == "online":
                        break
                    time.sleep(0.05)

                st_online = ctrl.get_state()
                self.assertEqual(st_online["gate"]["total_online"], 2)
                self.assertFalse(st_online["gate"]["can_enter_step2"])

                self.assertTrue(ctrl.test_peer(peer_key)["ok"])
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    st = ctrl.get_state()
                    if not st["test_busy"] and st["gate"]["can_enter_step2"]:
                        break
                    time.sleep(0.08)

                st_unlocked = ctrl.get_state()
                self.assertTrue(st_unlocked["gate"]["can_enter_step2"])
                self.assertTrue(st_unlocked["gate"]["step2_unlocked"])
                self.assertTrue(st_unlocked["step2"]["can_start_bridge"])
                self.assertEqual(len(st_unlocked["step2"]["target_hosts"]), 1)
            finally:
                ctrl.shutdown()
                remote_host.stop()

    def test_custom_vps_store_and_udp_relay_connect(self) -> None:
        import tempfile
        from civ6_p2p.glass_gui import GlassAppController
        from civ6_p2p.vps_store import VpsNodeStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store_file = Path(tmpdir) / "vps_nodes.json"
            ctrl = GlassAppController(start_bg_poller=False, vps_store_path=store_file)
            relay = RelayServer(listen_port=0)
            host_node = P2PNode(nickname="VpsHost", role="host", listen_port=0, room_key="vps-secret")
            try:
                self.assertEqual(ctrl.get_state()["vps_nodes"], [])

                r1 = ctrl.add_vps_node("香港节点", "hk.myvps.example", "easytier")
                self.assertTrue(r1["ok"])
                self.assertEqual(r1["node"]["address"], "tcp://hk.myvps.example:11010")

                rport = relay.start()
                host_node.start()
                host_node.connect_relay(f"127.0.0.1:{rport}", "vps-civ-room")

                r2 = ctrl.add_vps_node("自建UDP中继", f"127.0.0.1:{rport}", "udp_relay")
                self.assertTrue(r2["ok"])
                self.assertEqual(r2["node"]["address"], f"127.0.0.1:{rport}")
                self.assertEqual(r2["node"]["kind"], "udp_relay")

                reloaded = VpsNodeStore(path=store_file).list_nodes()
                self.assertEqual(len(reloaded), 2)

                ctrl.start_node(role="client", nickname="VpsClient", port_text="0", room_key="vps-secret")
                conn = ctrl.connect_easytier(r2["node"]["label"], "vps-civ-room")
                self.assertTrue(conn["ok"])
                self.assertEqual(conn["kind"], "udp_relay")

                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    st = ctrl.get_state()
                    if st["peers"] and st["peers"][0]["status"] == "online":
                        break
                    time.sleep(0.05)

                st = ctrl.get_state()
                self.assertEqual(len(st["peers"]), 1)
                self.assertEqual(st["peers"][0]["nickname"], "VpsHost")
                self.assertEqual(st["et_status_level"], "connected")

                ctrl.disconnect_easytier()
                self.assertTrue(ctrl.remove_vps_node(r1["node"]["id"])["ok"])
                self.assertEqual(len(VpsNodeStore(path=store_file).list_nodes()), 1)

                conn2 = ctrl.connect_easytier(r2["node"]["label"], "vps-civ-room")
                self.assertTrue(conn2["ok"])
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    st2 = ctrl.get_state()
                    if st2["peers"] and st2["peers"][0]["status"] == "online":
                        break
                    time.sleep(0.05)
                st2 = ctrl.get_state()
                self.assertEqual(len(st2["peers"]), 1)
                self.assertEqual(st2["peers"][0]["nickname"], "VpsHost")
                self.assertEqual(st2["peers"][0]["status"], "online")
                self.assertTrue(ctrl.test_peer(st2["peers"][0]["peer_key"])["ok"])
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    st3 = ctrl.get_state()
                    if not st3["test_busy"] and st3["gate"]["can_enter_step2"]:
                        break
                    time.sleep(0.08)
                self.assertTrue(ctrl.get_state()["gate"]["can_enter_step2"])
            finally:
                ctrl.shutdown()
                host_node.stop()
                relay.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
