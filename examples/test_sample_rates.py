#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采样率测试脚本
测试不同采样率下的逻辑分析仪性能

支持的采样率（从小到大）：
1. 10kHz   - 分频比: 2700  (适合低频信号，长时间采样)
2. 50kHz   - 分频比: 540   (适合中低频信号)
3. 100kHz  - 分频比: 270   (默认采样率，平衡性能和精度)
4. 500kHz  - 分频比: 54    (适合中频信号)
5. 1MHz    - 分频比: 27    (适合高频信号)
6. 10MHz   - 分频比: 2.7   (接近最大采样率，需要分频比>=1)
7. 13.5MHz - 分频比: 2     (高频采样)
8. 27MHz   - 分频比: 1     (最大采样率，每个时钟周期采样)

注意：系统时钟频率为27MHz
"""

import serial
import time
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.read_data import (
    open_serial, send_command, CMD_START, CMD_STOP, 
    set_sample_rate, wait_for_data, SYS_CLK_FREQ
)

# 测试采样率列表（从小到大）
SAMPLE_RATES = [
    (10_000, "10kHz", "低频信号，长时间采样"),
    (50_000, "50kHz", "中低频信号"),
    (100_000, "100kHz", "默认采样率，平衡性能和精度"),
    (500_000, "500kHz", "中频信号"),
    (1_000_000, "1MHz", "高频信号"),
    (10_000_000, "10MHz", "接近最大采样率"),
    (13_500_000, "13.5MHz", "高频采样（分频比=2）"),
    (27_000_000, "27MHz", "最大采样率（分频比=1）"),
]

def test_sample_rate(ser: serial.Serial, target_rate: float, rate_name: str, description: str):
    """
    测试单个采样率
    
    参数:
        ser: 串口对象
        target_rate: 目标采样率 (Hz)
        rate_name: 采样率名称（用于显示）
        description: 采样率描述
    """
    print(f"\n{'='*60}")
    print(f"测试采样率: {rate_name} ({description})")
    print(f"{'='*60}")
    
    # 设置采样率
    try:
        actual_rate = set_sample_rate(ser, target_rate)
        time.sleep(0.1)  # 等待设置完成
        
        # 计算分频比
        divider = round(PLL_CLK_FREQ / actual_rate)
        print(f"  分频比: {divider}")
        print(f"  实际采样率: {actual_rate/1e6:.3f} MHz" if actual_rate >= 1e6 
              else f"  实际采样率: {actual_rate/1e3:.3f} kHz")
        
        # 开始采样
        print(f"\n  开始采样...")
        send_command(ser, CMD_START)
        time.sleep(0.1)  # 等待采样开始
        
        # 等待采样完成（等待缓冲区满或手动停止）
        print(f"  等待采样完成...")
        time.sleep(2.0)  # 等待2秒，让缓冲区填满
        
        # 停止采样
        send_command(ser, CMD_STOP)
        time.sleep(0.1)
        
        # 接收数据
        print(f"  接收数据...")
        data = wait_for_data(ser, timeout=5.0, show_progress=True)
        
        if data:
            print(f"  ✓ 成功接收 {len(data)} 字节数据")
            
            # 分析数据
            if len(data) > 0:
                # 检查数据是否有变化
                unique_values = len(set(data))
                print(f"  数据统计: 唯一值数量 = {unique_values}/{len(data)}")
                
                # 显示前几个字节
                print(f"  前10个字节: {data[:10]}")
        else:
            print(f"  ✗ 未接收到数据")
            
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python test_sample_rates.py <串口> [采样率索引]")
        print("\n可用采样率:")
        for i, (rate, name, desc) in enumerate(SAMPLE_RATES):
            print(f"  {i}: {name:10s} - {desc}")
        print("\n示例:")
        print("  python test_sample_rates.py COM3        # 测试所有采样率")
        print("  python test_sample_rates.py COM3 0       # 只测试10kHz")
        print("  python test_sample_rates.py COM3 2       # 只测试100kHz")
        sys.exit(1)
    
    port = sys.argv[1]
    
    # 确定要测试的采样率
    if len(sys.argv) >= 3:
        try:
            index = int(sys.argv[2])
            if 0 <= index < len(SAMPLE_RATES):
                test_rates = [SAMPLE_RATES[index]]
            else:
                print(f"错误: 采样率索引 {index} 超出范围 [0-{len(SAMPLE_RATES)-1}]")
                sys.exit(1)
        except ValueError:
            print(f"错误: 无效的采样率索引 '{sys.argv[2]}'")
            sys.exit(1)
    else:
        test_rates = SAMPLE_RATES
    
    # 打开串口
    print(f"打开串口: {port}")
    try:
        ser = open_serial(port)
        print("✓ 串口打开成功")
    except Exception as e:
        print(f"✗ 无法打开串口: {e}")
        sys.exit(1)
    
    try:
        # 测试每个采样率
        for rate, name, desc in test_rates:
            test_sample_rate(ser, rate, name, desc)
            time.sleep(0.5)  # 测试间隔
        
        print(f"\n{'='*60}")
        print("所有测试完成！")
        print(f"{'='*60}")
        
    finally:
        ser.close()
        print("\n串口已关闭")

if __name__ == "__main__":
    main()

