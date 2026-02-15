#!/usr/bin/env python3
import sys
import yaml
import os

print("=" * 60)
print("[*] fly - Environment Verification")
print("=" * 60)

# 1. Python版本
print(f"\n[OK] Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# 2. 核心包检查
packages = [
    'pydantic', 'fastapi', 'cv2', 'pymavlink',
    'ultralytics', 'torch', 'sounddevice', 'yaml'
]

print("\n[PACKAGES]")
failed_packages = []
for pkg in packages:
    try:
        if pkg == 'cv2':
            import cv2
            print(f"   [OK] opencv-python {cv2.__version__}")
        elif pkg == 'yaml':
            import yaml
            print(f"   [OK] PyYAML {yaml.__version__}")
        else:
            mod = __import__(pkg)
            version = getattr(mod, '__version__', 'installed')
            print(f"   [OK] {pkg:20s} {version}")
    except ImportError as e:
        print(f"   [FAIL] {pkg:20s} missing")
        failed_packages.append(pkg)

# 3. 配置文件检查
print("\n[CONFIG FILES]")
config_files = ['configs/dev.yaml', 'configs/fsm.yaml', 'configs/pc_mavlink.yaml']
missing_configs = []
for cfg in config_files:
    try:
        with open(cfg) as f:
            yaml.safe_load(f)
        print(f"   [OK] {cfg}")
    except Exception as e:
        print(f"   [FAIL] {cfg} ({str(e)[:30]})")
        missing_configs.append(cfg)

# 4. 核心模块导入检查
print("\n[MODULES]")
modules = [
    'apps.acquisition.config_utils',
    'apps.acquisition.run_acq',
    'apps.control.fsm_runner',
    'apps.service.server',
    'src.common.run_manager',
]

failed_modules = []
for mod_name in modules:
    try:
        __import__(mod_name)
        print(f"   [OK] {mod_name}")
    except Exception as e:
        print(f"   [FAIL] {mod_name} ({str(e)[:40]})")
        failed_modules.append(mod_name)

# 5. 关键文件检查
print("\n[KEY FILES]")
key_files = [
    'apps/dev_run.py',
    'apps/acquisition/run_acq.py',
    'apps/control/fsm_runner.py',
    'apps/service/server.py',
    'configs/dev.yaml',
    'yolov8n.pt'
]

for f in key_files:
    if os.path.exists(f):
        size = os.path.getsize(f) / (1024*1024)  # MB
        print(f"   [OK] {f:40s} ({size:.1f} MB)")
    else:
        print(f"   [SKIP] {f:40s} not found")

print("\n" + "=" * 60)
if not failed_packages and not failed_modules:
    print("[SUCCESS] Environment verified! All dependencies OK.")
elif len(failed_packages) <= 2:
    print(f"[WARNING] Missing {len(failed_packages)} packages, basic features available.")
else:
    print(f"[ERROR] Missing {len(failed_packages)} critical packages, reinstall required.")
print("=" * 60)
