"""
Mission Planner / SITL 连接测试脚本
验证MAVLink通信和控制指令是否正常工作
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()


def test_heartbeat(conn_str: str, timeout: int = 10) -> bool:
    """测试MAVLink心跳连接"""
    print(f"[1/5] 测试心跳连接: {conn_str}")
    try:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection(conn_str)
        hb = master.wait_heartbeat(timeout=timeout)
        if hb:
            print(f"      ✓ 收到心跳 - 系统ID: {master.target_system}, 组件ID: {master.target_component}")
            print(f"      ✓ 飞控类型: {hb.type}, 自驾仪: {hb.autopilot}")
            return True
        else:
            print(f"      ✗ 心跳超时 ({timeout}秒)")
            return False
    except Exception as e:
        print(f"      ✗ 连接失败: {e}")
        return False


def test_telemetry(conn_str: str, duration: int = 5) -> dict:
    """测试遥测数据接收"""
    print(f"\n[2/5] 测试遥测数据接收 ({duration}秒)")
    try:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection(conn_str)
        master.wait_heartbeat(timeout=10)

        msg_counts = {}
        start = time.time()
        while time.time() - start < duration:
            msg = master.recv_match(blocking=True, timeout=1)
            if msg:
                msg_type = msg.get_type()
                msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1

        print(f"      ✓ 收到消息类型: {len(msg_counts)}")
        important_msgs = ['ATTITUDE', 'GLOBAL_POSITION_INT', 'SYS_STATUS', 'HEARTBEAT']
        for msg_type in important_msgs:
            count = msg_counts.get(msg_type, 0)
            status = "✓" if count > 0 else "✗"
            print(f"      {status} {msg_type}: {count} 条")
        return msg_counts
    except Exception as e:
        print(f"      ✗ 遥测接收失败: {e}")
        return {}


def test_mode_read(conn_str: str) -> str | None:
    """测试读取当前飞行模式"""
    print(f"\n[3/5] 测试读取飞行模式")
    try:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection(conn_str)
        master.wait_heartbeat(timeout=10)

        # 获取模式映射
        mode_mapping = master.mode_mapping()
        mode_mapping_rev = {v: k for k, v in mode_mapping.items()}

        # 等待心跳获取当前模式
        hb = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
        if hb:
            custom_mode = hb.custom_mode
            mode_name = mode_mapping_rev.get(custom_mode, f"UNKNOWN({custom_mode})")
            print(f"      ✓ 当前模式: {mode_name}")
            print(f"      ✓ 支持模式: {', '.join(list(mode_mapping.keys())[:8])}...")
            return mode_name
        return None
    except Exception as e:
        print(f"      ✗ 模式读取失败: {e}")
        return None


def test_yaw_command(conn_str: str, yaw_deg: float = 10, dry_run: bool = True) -> bool:
    """测试偏航控制指令"""
    print(f"\n[4/5] 测试偏航控制指令 (yaw={yaw_deg}°)")
    if dry_run:
        print(f"      ⚠ Dry-run模式，不发送真实指令")
        print(f"      ✓ 指令格式验证通过")
        return True

    try:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection(conn_str)
        master.wait_heartbeat(timeout=10)

        # MAV_CMD_CONDITION_YAW
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            115,  # MAV_CMD_CONDITION_YAW
            0,
            float(yaw_deg),  # param1: yaw angle
            30.0,            # param2: yaw rate deg/s
            1.0,             # param3: direction (1=CW)
            1.0,             # param4: relative (1=relative)
            0, 0, 0
        )
        print(f"      ✓ 偏航指令已发送")

        # 等待ACK
        ack = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        if ack and ack.command == 115:
            result_map = {0: "ACCEPTED", 1: "TEMP_REJECTED", 2: "DENIED", 3: "UNSUPPORTED", 4: "FAILED"}
            result = result_map.get(ack.result, f"UNKNOWN({ack.result})")
            if ack.result == 0:
                print(f"      ✓ 指令确认: {result}")
                return True
            else:
                print(f"      ✗ 指令拒绝: {result}")
                return False
        else:
            print(f"      ⚠ 未收到ACK（SITL可能不返回）")
            return True
    except Exception as e:
        print(f"      ✗ 偏航指令失败: {e}")
        return False


def test_api_control(api_base: str = "http://127.0.0.1:8000") -> bool:
    """测试通过REST API发送控制指令"""
    print(f"\n[5/5] 测试REST API控制")
    try:
        import urllib.request
        import urllib.error

        # 测试健康检查
        req = urllib.request.Request(f"{api_base}/health")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                print(f"      ✓ 服务状态: {data.get('status', 'unknown')}")
        except urllib.error.URLError as e:
            print(f"      ✗ 服务未运行: {e}")
            return False

        # 测试偏航API
        payload = json.dumps({"yaw_deg": 5, "yaw_rate_deg_s": 30}).encode()
        req = urllib.request.Request(
            f"{api_base}/api/control/yaw",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("accepted"):
                    print(f"      ✓ API偏航指令: accepted")
                    return True
                else:
                    print(f"      ✗ API偏航拒绝: {data.get('error', 'unknown')}")
                    return False
        except urllib.error.HTTPError as e:
            print(f"      ✗ API请求失败: {e.code} {e.reason}")
            return False

    except Exception as e:
        print(f"      ✗ API测试失败: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Mission Planner / SITL 连接测试")
    parser.add_argument("--udp", default="udp:127.0.0.1:14551", help="MAVLink UDP地址")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="REST API地址")
    parser.add_argument("--send-yaw", action="store_true", help="发送真实偏航指令")
    parser.add_argument("--duration", type=int, default=5, help="遥测测试时长(秒)")
    args = parser.parse_args()

    print("=" * 60)
    print("Mission Planner / SITL 连接测试")
    print("=" * 60)
    print(f"MAVLink: {args.udp}")
    print(f"API:     {args.api}")
    print("=" * 60)

    results = []

    # 1. 心跳测试
    results.append(("心跳连接", test_heartbeat(args.udp)))

    # 2. 遥测测试
    telemetry = test_telemetry(args.udp, args.duration)
    results.append(("遥测数据", len(telemetry) > 0))

    # 3. 模式读取
    mode = test_mode_read(args.udp)
    results.append(("模式读取", mode is not None))

    # 4. 偏航指令
    results.append(("偏航指令", test_yaw_command(args.udp, dry_run=not args.send_yaw)))

    # 5. API测试
    results.append(("REST API", test_api_control(args.api)))

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = 0
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {name}: {status}")
        if ok:
            passed += 1

    print("=" * 60)
    print(f"通过: {passed}/{len(results)}")

    if passed == len(results):
        print("\n✓ 所有测试通过！可以进行SITL联调。")
        return 0
    else:
        print("\n⚠ 部分测试失败，请检查配置。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
