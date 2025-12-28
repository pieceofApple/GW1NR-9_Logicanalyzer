#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
占空比设置脚本
功能: 通过串口设置逻辑分析仪的频率输出占空比
"""

import serial
import struct
import sys
import time

# 命令定义
CMD_SET_DUTY = 0x08

# 系统时钟频率
SYS_CLK_FREQ = 27_000_000  # 27MHz


def parse_duty_arg(duty_str: str) -> float:
    """
    解析占空比参数（支持百分比或小数）
    
    参数:
        duty_str: 占空比字符串，例如 "50", "50%", "0.5"
    
    返回:
        占空比（0.0-1.0）
    """
    duty_str = duty_str.strip().rstrip('%')
    
    try:
        duty_value = float(duty_str)
        
        # 如果值大于1，假设是百分比
        if duty_value > 1.0:
            duty_value = duty_value / 100.0
        
        # 限制范围
        if duty_value < 0.0:
            duty_value = 0.0
        elif duty_value > 1.0:
            duty_value = 1.0
        
        return duty_value
    except ValueError:
        return None


def set_duty_cycle(ser: serial.Serial, target_freq_hz: float, duty_ratio: float) -> tuple:
    """
    设置占空比
    
    参数:
        ser: 串口对象
        target_freq_hz: 目标频率 (Hz) - 用于计算周期
        duty_ratio: 占空比 (0.0-1.0)
    
    返回:
        (实际占空比, 高电平时间（时钟周期数）)
    """
    # 计算完整周期（时钟周期数）
    period_cycles = int(SYS_CLK_FREQ / target_freq_hz)
    
    # 计算高电平时间（时钟周期数）
    duty_high_cycles = int(period_cycles * duty_ratio)
    
    # 限制范围：最小1个周期，最大周期-1（接近100%占空比）
    duty_high_cycles = max(1, min(duty_high_cycles, period_cycles - 1))
    
    # 转换为字节 (小端序)
    duty_bytes = struct.pack('<I', duty_high_cycles)
    
    # 发送命令和数据
    ser.write(bytes([CMD_SET_DUTY]) + duty_bytes)
    time.sleep(0.01)  # 短暂延迟
    
    # 计算实际占空比
    actual_duty = duty_high_cycles / period_cycles
    
    return (actual_duty, duty_high_cycles)


def main():
    if len(sys.argv) < 4:
        print("用法: python set_duty_cycle.py <串口> <频率(Hz)> <占空比>")
        print("\n示例:")
        print("  python set_duty_cycle.py COM11 10000 50      # 10kHz, 50%占空比")
        print("  python set_duty_cycle.py COM11 10000 25%     # 10kHz, 25%占空比")
        print("  python set_duty_cycle.py COM11 10000 0.75   # 10kHz, 75%占空比")
        print("\n占空比格式:")
        print("  - 百分比: 50, 50%, 25, 25%")
        print("  - 小数: 0.5, 0.25, 0.75")
        sys.exit(1)
    
    port = sys.argv[1]
    
    try:
        target_freq = float(sys.argv[2])
    except ValueError:
        print(f"✗ 错误: 频率参数 '{sys.argv[2]}' 格式不正确")
        sys.exit(1)
    
    duty_ratio = parse_duty_arg(sys.argv[3])
    if duty_ratio is None:
        print(f"✗ 错误: 占空比参数 '{sys.argv[3]}' 格式不正确")
        print("  支持格式: 50, 50%, 0.5")
        sys.exit(1)
    
    # 打开串口
    try:
        ser = serial.Serial(port, 115200, timeout=1.0)
        time.sleep(0.5)  # 等待串口稳定
        print(f"✓ 串口 {port} 已打开")
    except Exception as e:
        print(f"✗ 错误: 无法打开串口 {port}: {e}")
        sys.exit(1)
    
    try:
        # 设置占空比
        print(f"\n设置占空比:")
        print(f"  目标频率: {target_freq} Hz")
        print(f"  目标占空比: {duty_ratio*100:.2f}%")
        
        actual_duty, duty_high_cycles = set_duty_cycle(ser, target_freq, duty_ratio)
        
        print(f"\n✓ 占空比设置成功")
        print(f"  实际占空比: {actual_duty*100:.2f}%")
        print(f"  高电平时间: {duty_high_cycles} 个时钟周期 ({duty_high_cycles/SYS_CLK_FREQ*1e6:.2f} μs)")
        print(f"  完整周期: {int(SYS_CLK_FREQ/target_freq)} 个时钟周期 ({1/target_freq*1e6:.2f} μs)")
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
    finally:
        ser.close()
        print("\n串口已关闭")


if __name__ == "__main__":
    main()

