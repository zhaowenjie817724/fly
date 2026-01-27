"""
YOLOv8 模型量化脚本
将FP32模型转换为INT8 NCNN格式，用于树莓派部署

使用方法:
    python scripts/quantize_model.py --model yolov8n.pt --output models/
    python scripts/quantize_model.py --model yolov8n.pt --format ncnn --imgsz 416
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def quantize_ncnn(model_path: Path, output_dir: Path, imgsz: int, int8: bool) -> Path:
    """导出为NCNN格式（树莓派推荐）"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("错误: 需要安装 ultralytics")
        print("  pip install ultralytics")
        sys.exit(1)

    print(f"加载模型: {model_path}")
    model = YOLO(str(model_path))

    print(f"导出NCNN格式 (imgsz={imgsz}, int8={int8})")
    export_path = model.export(
        format="ncnn",
        imgsz=imgsz,
        half=False,
        int8=int8,
    )

    # 移动到输出目录
    export_dir = Path(export_path)
    target_dir = output_dir / export_dir.name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.move(str(export_dir), str(target_dir))

    print(f"✓ 导出完成: {target_dir}")
    return target_dir


def quantize_onnx(model_path: Path, output_dir: Path, imgsz: int, simplify: bool) -> Path:
    """导出为ONNX格式"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("错误: 需要安装 ultralytics")
        sys.exit(1)

    print(f"加载模型: {model_path}")
    model = YOLO(str(model_path))

    print(f"导出ONNX格式 (imgsz={imgsz}, simplify={simplify})")
    export_path = model.export(
        format="onnx",
        imgsz=imgsz,
        simplify=simplify,
        opset=12,
    )

    # 移动到输出目录
    target_path = output_dir / Path(export_path).name
    shutil.move(export_path, str(target_path))

    print(f"✓ 导出完成: {target_path}")
    return target_path


def quantize_tflite(model_path: Path, output_dir: Path, imgsz: int, int8: bool) -> Path:
    """导出为TFLite格式"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("错误: 需要安装 ultralytics")
        sys.exit(1)

    print(f"加载模型: {model_path}")
    model = YOLO(str(model_path))

    print(f"导出TFLite格式 (imgsz={imgsz}, int8={int8})")
    export_path = model.export(
        format="tflite",
        imgsz=imgsz,
        int8=int8,
    )

    # 移动到输出目录
    target_path = output_dir / Path(export_path).name
    shutil.move(export_path, str(target_path))

    print(f"✓ 导出完成: {target_path}")
    return target_path


def estimate_memory(model_path: Path, format_type: str, int8: bool) -> None:
    """估算模型内存占用"""
    size_mb = model_path.stat().st_size / (1024 * 1024)

    # 估算转换后大小
    if format_type == "ncnn" and int8:
        estimated_mb = size_mb * 0.5  # INT8约为FP32的1/4，但NCNN有额外开销
        runtime_mb = estimated_mb * 3  # 运行时约3倍
    elif format_type == "onnx":
        estimated_mb = size_mb * 1.1
        runtime_mb = estimated_mb * 4
    else:
        estimated_mb = size_mb
        runtime_mb = estimated_mb * 4

    print(f"\n内存估算:")
    print(f"  原始模型: {size_mb:.1f} MB")
    print(f"  转换后:   {estimated_mb:.1f} MB (估算)")
    print(f"  运行时:   {runtime_mb:.1f} MB (估算)")

    if runtime_mb > 500:
        print(f"  ⚠ 警告: 运行时内存可能超过500MB，树莓派2GB需注意")


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOv8 模型量化工具")
    parser.add_argument("--model", default="yolov8n.pt", help="输入模型路径")
    parser.add_argument("--output", default="models", help="输出目录")
    parser.add_argument("--format", choices=["ncnn", "onnx", "tflite", "all"], default="ncnn",
                        help="输出格式")
    parser.add_argument("--imgsz", type=int, default=416, help="输入图像尺寸")
    parser.add_argument("--int8", action="store_true", default=True, help="启用INT8量化")
    parser.add_argument("--no-int8", dest="int8", action="store_false", help="禁用INT8量化")
    args = parser.parse_args()

    # 查找模型
    repo_root = Path(__file__).resolve().parents[1]
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = repo_root / model_path
    if not model_path.exists():
        print(f"错误: 模型不存在: {model_path}")
        return 1

    # 创建输出目录
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("YOLOv8 模型量化")
    print("=" * 60)
    print(f"输入模型: {model_path}")
    print(f"输出目录: {output_dir}")
    print(f"输出格式: {args.format}")
    print(f"图像尺寸: {args.imgsz}")
    print(f"INT8量化: {args.int8}")
    print("=" * 60)

    # 内存估算
    estimate_memory(model_path, args.format, args.int8)

    print("\n开始转换...\n")

    results = []

    if args.format in ("ncnn", "all"):
        try:
            path = quantize_ncnn(model_path, output_dir, args.imgsz, args.int8)
            results.append(("NCNN", path, True))
        except Exception as e:
            print(f"✗ NCNN导出失败: {e}")
            results.append(("NCNN", None, False))

    if args.format in ("onnx", "all"):
        try:
            path = quantize_onnx(model_path, output_dir, args.imgsz, simplify=True)
            results.append(("ONNX", path, True))
        except Exception as e:
            print(f"✗ ONNX导出失败: {e}")
            results.append(("ONNX", None, False))

    if args.format in ("tflite", "all"):
        try:
            path = quantize_tflite(model_path, output_dir, args.imgsz, args.int8)
            results.append(("TFLite", path, True))
        except Exception as e:
            print(f"✗ TFLite导出失败: {e}")
            results.append(("TFLite", None, False))

    # 汇总
    print("\n" + "=" * 60)
    print("转换结果")
    print("=" * 60)
    for name, path, ok in results:
        if ok:
            size_mb = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)
            print(f"  ✓ {name}: {path} ({size_mb:.1f} MB)")
        else:
            print(f"  ✗ {name}: 失败")

    print("\n树莓派部署建议:")
    print("  1. 使用NCNN INT8格式")
    print("  2. 图像尺寸建议416x416或更小")
    print("  3. 确保有2GB Swap空间")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
