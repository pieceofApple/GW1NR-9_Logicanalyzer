#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频率设置脚本（优化版）
功能: 通过串口设置逻辑分析仪的频率输出
新特性: 可以在任何时候设置频率（包括采样过程中）
"""

import serial
import struct
import sys
import time

# 命令定义
CMD_SET_FREQ = 0x06

# 系统时钟频率
SYS_CLK_FREQ = 27_000_000  # 27MHz


def set_frequency(ser: serial.Serial, target_freq_hz: float) -> float:
    """
    设置频率输出（可以在任何时候调用，包括采样过程中）
    
    参数:
        ser: 串口对象
        target_freq_hz: 目标频率 (Hz)
    
    返回:
        实际输出频率
    """
    # 计算分频比
    # 分频比 = 27MHz / 目标频率 / 2
    divider = int(SYS_CLK_FREQ / target_freq_hz / 2)
    
    # 限制分频比范围 (最小为1，最大为2^32-1)
    divider = max(1, min(divider, 0xFFFFFFFF))
    
    # 转换为字节 (小端序)
    divider_bytes = struct.pack('<I', divider)
    
    # 发送命令和数据
    ser.write(bytes([CMD_SET_FREQ]) + divider_bytes)
    time.sleep(0.01)  # 短暂延迟
    
    # 计算实际频率
    actual_freq = SYS_CLK_FREQ / (divider * 2)
    
    error = abs(actual_freq - target_freq_hz)
    error_percent = (error / target_freq_hz * 100) if target_freq_hz > 0 else 0
    
    print(f"目标频率: {target_freq_hz:,.2f} Hz")
    print(f"分频比: {divider:,} (0x{divider:08X})")
    print(f"实际频率: {actual_freq:,.2f} Hz")
    print(f"频率误差: {error:.2f} Hz ({error_percent:.2f}%)")
    print("-" * 50)
    
    return actual_freq


def get_frequency_info(target_freq_hz: float) -> dict:
    """获取频率设置信息（不实际设置）"""
    divider = int(SYS_CLK_FREQ / target_freq_hz / 2)
    divider = max(1, min(divider, 0xFFFFFFFF))
    actual_freq = SYS_CLK_FREQ / (divider * 2)
    error = abs(actual_freq - target_freq_hz)
    error_percent = (error / target_freq_hz * 100) if target_freq_hz > 0 else 0
    
    return {
        'target': target_freq_hz,
        'divider': divider,
        'actual': actual_freq,
        'error': error,
        'error_percent': error_percent
    }


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python set_frequency.py <串口> [频率(Hz)] [选项]")
        print("示例: python set_frequency.py COM3 1000")
        print("      python set_frequency.py /dev/ttyUSB0 10000")
        print("\n选项:")
        print("  --info           只显示频率信息，不实际设置")
        print("  --scan <min> <max> <step>  频率扫描模式")
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
            # 频率扫描模式
            if len(sys.argv) < 6:
                print("✗ 错误: --scan 需要参数: <最小频率> <最大频率> <步进>")
                sys.exit(1)
            
            min_freq = float(sys.argv[sys.argv.index('--scan') + 1])
            max_freq = float(sys.argv[sys.argv.index('--scan') + 2])
            step = float(sys.argv[sys.argv.index('--scan') + 3])
            
            print(f"频率扫描: {min_freq} Hz ~ {max_freq} Hz, 步进: {step} Hz")
            print("=" * 50)
            
            freq = min_freq
            while freq <= max_freq:
                print(f"\n设置频率: {freq} Hz")
                set_frequency(ser, freq)
                time.sleep(1)  # 等待1秒观察输出
                freq += step
            
            print("\n✓ 频率扫描完成")
            
        elif info_mode:
            # 信息模式：只显示信息，不实际设置
            if len(sys.argv) < 3:
                print("✗ 错误: --info 模式需要指定频率")
                sys.exit(1)
            
            freq = float(sys.argv[2])
            info = get_frequency_info(freq)
            
            print("频率设置信息（不实际设置）:")
            print("=" * 50)
            print(f"目标频率: {info['target']:,.2f} Hz")
            print(f"分频比: {info['divider']:,} (0x{info['divider']:08X})")
            print(f"实际频率: {info['actual']:,.2f} Hz")
            print(f"频率误差: {info['error']:.2f} Hz ({info['error_percent']:.2f}%)")
            
        else:
            # 正常模式：设置频率
            freq = float(sys.argv[2]) if len(sys.argv) > 2 else 10000  # 默认 10kHz
            
            # 验证频率范围
            if freq <= 0:
                print("✗ 错误: 频率必须大于0")
                sys.exit(1)
            
            max_freq = SYS_CLK_FREQ / 2  # 理论最大频率
            if freq > max_freq:
                print(f"⚠ 警告: 频率 {freq} Hz 超过理论最大值 {max_freq:.2f} Hz")
            
            # 设置频率
            set_frequency(ser, freq)
            print("✓ 频率设置完成！")
            print("\n提示: 可以在任何时候（包括采样过程中）设置频率")
        
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
