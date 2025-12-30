#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采样率设置脚本
功能: 通过串口设置FPGA的硬件采样率
"""

import serial
import struct
import sys
import time

# 命令定义
CMD_SET_SAMPLE_RATE = 0x07

# 系统时钟频率
SYS_CLK_FREQ = 27_000_000  # 27MHz


def set_sample_rate(ser: serial.Serial, target_sample_rate_hz: float) -> float:
    """
    设置FPGA采样率（可以在任何时候调用，包括采样过程中）
    
    参数:
        ser: 串口对象
        target_sample_rate_hz: 目标采样率 (Hz)
    
    返回:
        实际采样率 (Hz)
    """
    # 计算分频比
    # 分频比 = 27MHz / 目标采样率
    divider = int(SYS_CLK_FREQ / target_sample_rate_hz)
    divider = max(1, min(divider, 0xFFFFFFFF))
    
    # 转换为字节 (小端序)
    divider_bytes = struct.pack('<I', divider)
    
    # 发送命令和数据
    ser.write(bytes([CMD_SET_SAMPLE_RATE]) + divider_bytes)
    time.sleep(0.01)
    
    # 计算实际采样率
    actual_rate = SYS_CLK_FREQ / divider
    
    error = abs(actual_rate - target_sample_rate_hz)
    error_percent = (error / target_sample_rate_hz * 100) if target_sample_rate_hz > 0 else 0
    
    print(f"目标采样率: {target_sample_rate_hz/1e6:.2f} MHz")
    print(f"分频比: {divider:,} (0x{divider:08X})")
    print(f"实际采样率: {actual_rate/1e6:.2f} MHz")
    print(f"采样率误差: {error:.2f} Hz ({error_percent:.2f}%)")
    print("-" * 50)
    
    return actual_rate


def get_sample_rate_info(target_sample_rate_hz: float) -> dict:
    """获取采样率设置信息（不实际设置）"""
    divider = int(SYS_CLK_FREQ / target_sample_rate_hz)
    divider = max(1, min(divider, 0xFFFFFFFF))
    actual_rate = SYS_CLK_FREQ / divider
    error = abs(actual_rate - target_sample_rate_hz)
    error_percent = (error / target_sample_rate_hz * 100) if target_sample_rate_hz > 0 else 0
    
    return {
        'target': target_sample_rate_hz,
        'divider': divider,
        'actual': actual_rate,
        'error': error,
        'error_percent': error_percent
    }


def parse_sample_rate(rate_str: str) -> float:
    """
    解析采样率字符串，支持预设值和数字
    
    参数:
        rate_str: 采样率字符串，如 "1M", "100k", "1000000" 等
    
    返回:
        采样率 (Hz)
    """
    rate_str = rate_str.strip().upper()
    
    # 预设值映射
    presets = {
        '27M': 27_000_000,
        '13.5M': 13_500_000,
        '1M': 1_000_000,
        '500K': 500_000,
        '100K': 100_000,
        '50K': 50_000,
        '10K': 10_000,
        '1K': 1_000,
    }
    
    # 检查预设值
    if rate_str in presets:
        return presets[rate_str]
    
    # 处理带单位的字符串
    if rate_str.endswith('M'):
        return float(rate_str[:-1]) * 1_000_000
    elif rate_str.endswith('K'):
        return float(rate_str[:-1]) * 1_000
    elif rate_str.endswith('HZ'):
        return float(rate_str[:-2])
    else:
        # 纯数字
        return float(rate_str)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python set_sample_rate.py <串口> [采样率] [选项]")
        print("示例: python set_sample_rate.py COM3 1000000")
        print("      python set_sample_rate.py COM3 1M")
        print("      python set_sample_rate.py /dev/ttyUSB0 100k")
        print("\n采样率格式:")
        print("  - 数字: 1000000 (1MHz)")
        print("  - 预设值: 27M, 13.5M, 1M, 500k, 100k, 50k, 10k, 1k")
        print("\n选项:")
        print("  --info           只显示采样率信息，不实际设置")
        print("  --scan <min> <max> <step>  采样率扫描模式")
        sys.exit(1)
    
    port = sys.argv[1]
    
    # 检查是否是信息模式
    info_mode = '--info' in sys.argv
    scan_mode = '--scan' in sys.argv
    
    try:
        # 打开串口（如果不是信息模式）
        if not info_mode:
            ser = serial.Serial(port, 115200, timeout=1)
            print(f"已连接到串口: {port}")
            print(f"波特率: 115200")
            print("=" * 50)
        
        if scan_mode:
            # 采样率扫描模式
            if len(sys.argv) < 6:
                print("✗ 错误: --scan 需要参数: <最小采样率> <最大采样率> <步进>")
                sys.exit(1)
            
            min_rate = float(sys.argv[sys.argv.index('--scan') + 1])
            max_rate = float(sys.argv[sys.argv.index('--scan') + 2])
            step = float(sys.argv[sys.argv.index('--scan') + 3])
            
            print(f"采样率扫描: {min_rate/1e6:.2f} MHz ~ {max_rate/1e6:.2f} MHz, 步进: {step/1e6:.2f} MHz")
            print("=" * 50)
            
            rate = min_rate
            while rate <= max_rate:
                print(f"\n设置采样率: {rate/1e6:.2f} MHz")
                set_sample_rate(ser, rate)
                time.sleep(1)  # 等待1秒观察
                rate += step
            
            print("\n✓ 采样率扫描完成")
            
        elif info_mode:
            # 信息模式：只显示信息，不实际设置
            if len(sys.argv) < 3:
                print("✗ 错误: --info 模式需要指定采样率")
                sys.exit(1)
            
            try:
                rate = parse_sample_rate(sys.argv[2])
            except (ValueError, KeyError):
                print("✗ 错误: 采样率格式不正确")
                print("  支持格式: 数字 (如 1000000) 或预设值 (如 1M, 100k)")
                sys.exit(1)
            info = get_sample_rate_info(rate)
            
            print("采样率设置信息（不实际设置）:")
            print("=" * 50)
            print(f"目标采样率: {info['target']/1e6:.2f} MHz")
            print(f"分频比: {info['divider']:,} (0x{info['divider']:08X})")
            print(f"实际采样率: {info['actual']/1e6:.2f} MHz")
            print(f"采样率误差: {info['error']:.2f} Hz ({info['error_percent']:.2f}%)")
            
        else:
            # 正常模式：设置采样率
            if len(sys.argv) > 2:
                try:
                    rate = parse_sample_rate(sys.argv[2])
                except (ValueError, KeyError):
                    print("✗ 错误: 采样率格式不正确")
                    print("  支持格式: 数字 (如 1000000) 或预设值 (如 1M, 100k)")
                    sys.exit(1)
            else:
                rate = 100_000  # 默认 100kHz
            
            # 验证采样率范围
            if rate <= 0:
                print("✗ 错误: 采样率必须大于0")
                sys.exit(1)
            
            if rate > SYS_CLK_FREQ:
                print(f"⚠ 警告: 采样率 {rate/1e6:.2f} MHz 超过系统时钟 {SYS_CLK_FREQ/1e6:.2f} MHz")
            
            # 设置采样率
            set_sample_rate(ser, rate)
            print("✓ 采样率设置完成！")
            print("\n提示: 可以在任何时候（包括采样过程中）设置采样率")
        
        # 关闭串口
        if not info_mode:
            ser.close()
        
    except serial.SerialException as e:
        print(f"✗ 串口错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"✗ 参数错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n用户中断")
        if not info_mode:
            ser.close()
        sys.exit(0)
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        if not info_mode:
            ser.close()
        sys.exit(1)


if __name__ == '__main__':
    main()

