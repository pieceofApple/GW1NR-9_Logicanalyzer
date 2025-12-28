#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逻辑分析仪数据读取脚本（优化版）
功能: 连接FPGA，开始采样，自动接收数据，并显示波形
适配新逻辑: 发送0x01后立即采样，采样完成后自动发送数据
"""

import serial
import struct
import time
import sys
import threading
import matplotlib.pyplot as plt
import matplotlib
import sqlite3
from typing import List, Tuple, Optional

# 配置matplotlib支持中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 命令定义
CMD_START = 0x01
CMD_STOP = 0x02
CMD_TRIGGER = 0x04  # 触发配置命令
CMD_CONFIG = 0x05   # 触发配置数据
CMD_SET_FREQ = 0x06
CMD_SET_SAMPLE_RATE = 0x07  # 设置采样率
CMD_SET_DUTY = 0x08  # 设置占空比

# 采样参数
SYS_CLK_FREQ = 27_000_000   # 系统时钟 27MHz（采样时钟）
SAMPLE_RATE = SYS_CLK_FREQ  # 采样时钟频率（使用系统时钟）
DEFAULT_SAMPLE_RATE = 100_000  # 默认采样率 100kHz（与FPGA默认值一致）
BUFFER_SIZE = 49152  # 48KB 缓冲区 (充分利用BRAM资源，384K bits / 468K bits = 82.1%)
CHANNELS = 8  # 8个通道


def open_serial(port: str, baudrate: int = 115200, timeout: float = 1.0) -> serial.Serial:
    """打开串口"""
    try:
        ser = serial.Serial(port, baudrate, timeout=timeout, write_timeout=5.0)
        print(f"✓ 串口已打开: {port} @ {baudrate}")
        return ser
    except serial.SerialException as e:
        print(f"✗ 无法打开串口 {port}: {e}")
        sys.exit(1)


def wait_for_startup(ser: serial.Serial, timeout: float = 2.0) -> bool:
    """等待FPGA发送启动消息 'start'"""
    print("等待FPGA启动消息...")
    start_time = time.time()
    buffer = b''
    
    while time.time() - start_time < timeout:
        if ser.in_waiting > 0:
            buffer += ser.read(ser.in_waiting)
            if b'start' in buffer:
                print("✓ 收到启动消息: 'start'")
                return True
        time.sleep(0.01)
    
    print("⚠ 未收到启动消息（可能已启动，继续...）")
    return False


def send_command(ser: serial.Serial, cmd: int, data: bytes = b'') -> None:
    """发送命令"""
    # 等待串口输出缓冲区有空间（避免缓冲区满导致写入超时）
    try:
        while hasattr(ser, 'out_waiting') and ser.out_waiting > 1000:  # 如果输出缓冲区超过1KB，等待
            time.sleep(0.01)
    except AttributeError:
        # 某些串口实现可能不支持out_waiting，忽略
        pass
    ser.write(bytes([cmd]) + data)
    ser.flush()  # 确保数据发送
    time.sleep(0.01)  # 短暂延迟


def configure_trigger(ser: serial.Serial, trigger_type: int, trigger_mask: int = 0xFF, trigger_pattern: int = 0x00, pre_trigger_count: int = 0) -> None:
    """
    配置触发参数
    
    参数:
        ser: 串口对象
        trigger_type: 触发类型
            0 = 上升沿触发 (rising)
            1 = 下降沿触发 (falling)
            2 = 模式触发 (pattern)
            3 = 双边沿触发 (both)
        trigger_mask: 触发通道掩码（1=启用该通道触发），默认0xFF（所有通道）
        trigger_pattern: 触发模式（用于模式触发），默认0x00
        pre_trigger_count: 预触发样本数（触发前存储的样本数），默认0（无预触发）
    """
    # 发送CMD_TRIGGER命令
    send_command(ser, CMD_TRIGGER)
    time.sleep(0.01)  # 等待命令处理
    
    # 发送触发配置参数：
    # trigger_type (1字节) + trigger_mask (1字节) + trigger_pattern (1字节)
    # 如果使用触发（trigger_type != 0 或 trigger_mask != 0），则还需要发送 pre_trigger_count (2字节，小端序)
    if trigger_type == 0 and trigger_mask == 0:
        # 立即触发，不需要预触发
        config_data = struct.pack('<BBB', trigger_type, trigger_mask, trigger_pattern)
    else:
        # 使用触发，需要发送预触发点数
        config_data = struct.pack('<BBBH', trigger_type, trigger_mask, trigger_pattern, pre_trigger_count)
    
    send_command(ser, CMD_CONFIG, config_data)
    time.sleep(0.05)  # 等待配置完成
    
    trigger_type_names = ['上升沿', '下降沿', '模式', '双边沿']
    print(f"✓ 触发已配置: {trigger_type_names[trigger_type] if trigger_type < len(trigger_type_names) else '未知'}")
    print(f"  触发通道掩码: 0x{trigger_mask:02X} (二进制: {bin(trigger_mask)[2:].zfill(8)})")
    if trigger_type == 2:  # 模式触发
        print(f"  触发模式: 0x{trigger_pattern:02X} (二进制: {bin(trigger_pattern)[2:].zfill(8)})")
    if pre_trigger_count > 0:
        print(f"  预触发样本数: {pre_trigger_count}")


def start_sampling(ser: serial.Serial, wait_for_trigger: bool = False) -> None:
    """
    开始采样
    
    参数:
        ser: 串口对象
        wait_for_trigger: 是否等待触发（当前FPGA实现会立即开始，此参数为预留）
    """
    print("发送开始采样命令 (0x01)...")
    send_command(ser, CMD_START)
    if wait_for_trigger:
        print("✓ 采样已启动（等待触发条件满足）")
    else:
        print("✓ 采样已启动（立即开始，无需等待触发）")


def stop_sampling(ser: serial.Serial) -> None:
    """停止采样"""
    print("发送停止采样命令 (0x02)...")
    send_command(ser, CMD_STOP)
    print("✓ 采样已停止")


def send_test_data_continuous(ser: serial.Serial, stop_flag: threading.Event = None) -> None:
    """
    持续发送测试数据（0~255递增序列，256字节循环），直到采样结束
    
    Args:
        ser: 串口对象
        stop_flag: 外部停止标志（如果提供，用于外部控制停止）
    """
    print(f"\n开始持续发送测试数据 (0~255递增序列，256字节循环)...")
    print("  提示: 如果CH1连接到UART的RX引脚，可以抓取这些测试数据")
    
    total_sent = 0
    base_index = 0
    start_time = time.time()
    last_progress_time = start_time
    first_send = True
    
    while True:
        # 检查停止标志
        if stop_flag is not None and stop_flag.is_set():
            break
        
        # 检查超时（最多5分钟）
        if time.time() - start_time > 300:
            print(f"\n⚠ 发送超时，停止发送 (已发送: {total_sent} 字节)")
            break
        
        # 生成测试数据：0~255递增序列（256字节）
        test_data = bytes([(base_index + i) % 256 for i in range(256)])
        
        try:
            # 检查串口输出缓冲区，如果太满则等待（某些串口可能不支持out_waiting）
            try:
                if hasattr(ser, 'out_waiting'):
                    while ser.out_waiting > 2000:  # 如果输出缓冲区超过2KB，等待
                        time.sleep(0.01)
                        if stop_flag is not None and stop_flag.is_set():
                            break
            except (AttributeError, OSError):
                # 某些串口实现可能不支持out_waiting，忽略
                pass
            
            # 发送测试数据
            bytes_written = ser.write(test_data)
            if bytes_written > 0:
                ser.flush()
                total_sent += bytes_written
                base_index += len(test_data)
                
                # 首次发送时显示确认信息
                if first_send:
                    print(f"  ✓ 首次发送成功: {bytes_written} 字节")
                    first_send = False
                
                # 每1秒显示一次进度
                current_time = time.time()
                if current_time - last_progress_time >= 1.0:
                    print(f"  已发送: {total_sent} 字节 (速率: {total_sent/(current_time-start_time):.1f} 字节/秒)...", end='\r', flush=True)
                    last_progress_time = current_time
            else:
                # 如果没有写入任何数据，可能是缓冲区满，稍等再试
                if first_send:
                    print(f"  ⚠ 警告: 首次发送失败，bytes_written = {bytes_written}")
                time.sleep(0.05)
        except Exception as e:
            print(f"\n✗ 发送测试数据时出错: {e}")
            import traceback
            traceback.print_exc()
            break
        
        # 短暂延迟，控制发送速率（约100字节/秒，适合采样）
        time.sleep(0.01)
    
    if total_sent > 0:
        print(f"\n✓ 测试数据发送完成 (总计: {total_sent} 字节)")
        preview_data = bytes([i % 256 for i in range(min(16, 256))])
        print(f"  数据预览 (前16字节): {' '.join([f'{b:02X}' for b in preview_data[:16]])}")


def set_frequency(ser: serial.Serial, target_freq_hz: float) -> float:
    """设置频率输出（可以在任何时候调用，包括采样过程中）"""
    # 计算分频比
    divider = int(27_000_000 / target_freq_hz / 2)
    divider = max(1, min(divider, 0xFFFFFFFF))
    
    # 转换为字节 (小端序)
    divider_bytes = struct.pack('<I', divider)
    
    # 发送命令和数据
    send_command(ser, CMD_SET_FREQ, divider_bytes)
    
    # 计算实际频率
    actual_freq = 27_000_000 / (divider * 2)
    print(f"✓ 频率已设置: {target_freq_hz} Hz → {actual_freq:.2f} Hz (分频比: {divider})")
    return actual_freq


def parse_duty_arg(duty_str: str) -> Optional[float]:
    """
    解析占空比参数（支持百分比或小数）
    
    参数:
        duty_str: 占空比字符串，例如 "50", "50%", "0.5"
    
    返回:
        占空比（0.0-1.0），如果解析失败返回None
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
    period_cycles = int(27_000_000 / target_freq_hz)
    
    # 计算高电平时间（时钟周期数）
    duty_high_cycles = int(period_cycles * duty_ratio)
    
    # 限制范围：最小1个周期，最大周期-1（接近100%占空比）
    duty_high_cycles = max(1, min(duty_high_cycles, period_cycles - 1))
    
    # 转换为字节 (小端序)
    duty_bytes = struct.pack('<I', duty_high_cycles)
    
    # 发送命令和数据
    send_command(ser, CMD_SET_DUTY, duty_bytes)
    
    # 计算实际占空比
    actual_duty = duty_high_cycles / period_cycles
    
    return (actual_duty, duty_high_cycles)


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
        '27M': 27_000_000,  # 系统时钟频率（最大采样率）
        '13.5M': 13_500_000,  # 27MHz / 2
        '9M': 9_000_000,  # 27MHz / 3
        '6.75M': 6_750_000,  # 27MHz / 4
        '5.4M': 5_400_000,  # 27MHz / 5
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
    # 分频比 = 27MHz (系统时钟) / 目标采样率
    # 使用四舍五入而不是截断，以获得更准确的采样率
    divider = round(SYS_CLK_FREQ / target_sample_rate_hz)
    divider = max(1, min(int(divider), 0xFFFFFFFF))
    
    # 转换为字节 (小端序)
    divider_bytes = struct.pack('<I', divider)
    
    # 发送命令和数据
    send_command(ser, CMD_SET_SAMPLE_RATE, divider_bytes)
    
    # 计算实际采样率
    actual_rate = SYS_CLK_FREQ / divider
    if target_sample_rate_hz >= 1e6:
        print(f"✓ 采样率已设置: {target_sample_rate_hz/1e6:.2f} MHz → {actual_rate/1e6:.2f} MHz (分频比: {divider})")
    else:
        print(f"✓ 采样率已设置: {target_sample_rate_hz/1e3:.2f} kHz → {actual_rate/1e3:.2f} kHz (分频比: {divider})")
    return actual_rate


def wait_for_data(ser: serial.Serial, expected_size: int = BUFFER_SIZE, 
                  timeout: float = 60.0, show_progress: bool = True) -> List[int]:
    """
    等待并接收采样数据
    新逻辑: 采样完成后自动发送数据，无需发送READ命令
    """
    print(f"\n等待采样完成并接收数据（期望 {expected_size} 字节）...")
    print("提示: 采样会在缓冲区满时自动停止，然后自动发送数据")
    
    data = []
    start_time = time.time()
    last_size = 0
    no_data_timeout = 5.0  # 如果5秒没有新数据，认为传输完成（增加超时时间）
    last_data_time = time.time()
    first_data_time = None
    
    if show_progress:
        print("接收数据中...", end='', flush=True)
    
    while True:
        current_time = time.time()
        
        # 检查总超时（增加到60秒，给低采样率足够时间）
        if current_time - start_time > timeout:
            print(f"\n⚠ 总超时 ({timeout}s): 收到 {len(data)} 字节")
            if len(data) < expected_size:
                print(f"⚠ 警告: 只收到 {len(data)} 字节，期望 {expected_size} 字节")
                print(f"  可能原因:")
                print(f"  1. 采样时间不够（采样率太低）")
                print(f"  2. 使用了触发模式，但触发条件未满足")
                print(f"  3. 采样被提前停止")
            break
        
        # 检查是否有新数据
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            data.extend(chunk)
            last_data_time = current_time
            if first_data_time is None:
                first_data_time = current_time
                print(f"\n✓ 开始接收数据（采样完成，开始传输）")
            
            if show_progress:
                progress = (len(data) / expected_size * 100) if expected_size > 0 else 0
                print(f"\r接收数据中... {len(data)}/{expected_size} 字节 ({progress:.1f}%)", end='', flush=True)
            
            # 如果收到足够的数据，等待一小段时间确认没有更多数据
            if len(data) >= expected_size:
                time.sleep(0.2)  # 等待200ms确认没有更多数据
                if ser.in_waiting == 0:
                    print(f"\n✓ 已收到完整数据: {len(data)} 字节")
                    break
        else:
            # 如果没有新数据
            if len(data) > 0:
                # 如果已经收到一些数据，但还没达到期望值
                if current_time - last_data_time > no_data_timeout:
                    # 已经有数据且超过5秒没有新数据，认为传输完成
                    if show_progress:
                        print(f"\n⚠ 数据传输中断（{current_time - last_data_time:.1f}秒无新数据）")
                        print(f"  已收到: {len(data)} 字节，期望: {expected_size} 字节")
                        if len(data) < expected_size:
                            print(f"  ⚠ 警告: 数据不完整！可能采样被提前停止或传输中断")
                    break
            elif current_time - start_time > 10.0:
                # 如果10秒还没收到任何数据，提示可能的问题
                print(f"\n⚠ 警告: 10秒未收到任何数据")
                print(f"  可能原因:")
                print(f"  1. 使用了触发模式，但触发条件未满足（采样未开始）")
                print(f"  2. FPGA未开始采样")
                print(f"  3. 串口通信问题")
                # 继续等待，不立即退出
        
        time.sleep(0.01)
    
    if show_progress:
        print(f"\n✓ 总共收到 {len(data)} 字节数据")
        if len(data) < expected_size:
            print(f"  ⚠ 警告: 数据不完整！期望 {expected_size} 字节，实际收到 {len(data)} 字节")
            print(f"  样本数: {len(data)} 个（期望 {expected_size} 个）")
    
    return data


def parse_channels(data: List[int]) -> List[List[int]]:
    """解析每个通道的数据"""
    channels = [[] for _ in range(CHANNELS)]
    
    for byte in data:
        for ch in range(CHANNELS):
            bit = (byte >> ch) & 1
            channels[ch].append(bit)
    
    return channels


def plot_waveforms(channels: List[List[int]], sample_rate: float = DEFAULT_SAMPLE_RATE) -> None:
    """绘制波形图，并在标题中显示频率信息"""
    samples = len(channels[0])
    if samples == 0:
        print("⚠ 没有数据可显示")
        return
    
    # 计算采样时长
    sample_period = 1.0 / sample_rate  # 每个样本的周期（秒）
    total_duration = samples / sample_rate  # 总采样时长（秒）
    
    time_axis = [i / sample_rate * 1e6 for i in range(samples)]  # 转换为微秒
    
    fig, axes = plt.subplots(CHANNELS, 1, figsize=(12, 10), sharex=True)
    if CHANNELS == 1:
        axes = [axes]
    
    # 构建标题，包含采样时长信息
    title = f'逻辑分析仪波形\n'
    if sample_rate >= 1e6:
        title += f'采样率: {sample_rate/1e6:.2f} MHz | '
    else:
        title += f'采样率: {sample_rate/1e3:.2f} kHz | '
    if total_duration >= 1:
        title += f'采样时长: {total_duration:.3f} s | '
    elif total_duration >= 1e-3:
        title += f'采样时长: {total_duration*1e3:.3f} ms | '
    else:
        title += f'采样时长: {total_duration*1e6:.3f} μs | '
    title += f'样本数: {samples:,}'
    
    fig.suptitle(title, fontsize=12)
    
    for ch in range(CHANNELS):
        channel_data = channels[ch]
        
        # 计算该通道的频率
        frequency = calculate_signal_frequency(channel_data, sample_rate)
        
        # 绘制波形
        axes[ch].plot(time_axis, channel_data, drawstyle='steps-post', linewidth=0.8)
        
        # 构建Y轴标签，包含频率信息
        ylabel = f'CH{ch}'
        if frequency is not None:
            if frequency >= 1e6:
                ylabel += f'\n{frequency/1e6:.3f} MHz'
            elif frequency >= 1e3:
                ylabel += f'\n{frequency/1e3:.3f} kHz'
            else:
                ylabel += f'\n{frequency:.2f} Hz'
        else:
            ylabel += '\n(恒定电平)'
        
        axes[ch].set_ylabel(ylabel, fontsize=10)
        axes[ch].set_ylim(-0.5, 1.5)
        axes[ch].grid(True, alpha=0.3)
        axes[ch].set_yticks([0, 1])
    
    axes[-1].set_xlabel('Time (μs)', fontsize=12)
    plt.tight_layout()
    plt.show()


def save_data_to_file(data: List[int], filename: str = 'logic_analyzer_data.bin') -> None:
    """保存数据到文件"""
    with open(filename, 'wb') as f:
        f.write(bytes(data))
    print(f"✓ 数据已保存到: {filename}")


def export_to_vcd(channels: List[List[int]], sample_rate: float, filename: str = 'logic_analyzer_data.vcd') -> None:
    """
    导出数据为 VCD (Value Change Dump) 格式，PulseView 支持此格式
    
    参数:
        channels: 通道数据列表（每个通道是一个0/1列表）
        sample_rate: 采样率 (Hz)
        filename: 输出文件名
    """
    with open(filename, 'w', encoding='utf-8') as f:
        # VCD 文件头
        f.write("$date\n")
        from datetime import datetime
        f.write(f"    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("$end\n")
        f.write("$version\n")
        f.write("    FPGA Logic Analyzer Export\n")
        f.write("$end\n")
        f.write("$comment\n")
        f.write(f"    Sample Rate: {sample_rate} Hz\n")
        f.write(f"    Channels: {len(channels)}\n")
        f.write(f"    Samples: {len(channels[0]) if channels else 0}\n")
        f.write("$end\n")
        f.write("$timescale 1ps $end\n")  # 使用1ps作为时间单位，可以精确表示
        
        # 定义变量
        f.write("$scope module logic_analyzer $end\n")
        var_names = []
        for i in range(len(channels)):
            var_id = f"ch{i}"
            var_names.append(var_id)
            f.write(f"$var wire 1 {var_id} CH{i} $end\n")
        f.write("$upscope $end\n")
        f.write("$enddefinitions $end\n")
        
        # 计算时间步长（以ps为单位）
        time_step_ps = int(1e12 / sample_rate)  # 每个样本的时间（皮秒）
        
        # 写入数据变化
        current_time = 0
        prev_values = [None] * len(channels)
        
        # 写入初始值（时间0）
        f.write(f"#{current_time}\n")
        for i in range(len(channels)):
            if len(channels[i]) > 0:
                value = channels[i][0]
                f.write(f"{value}{var_names[i]}\n")
                prev_values[i] = value
        
        # 遍历所有样本，只在值变化时写入
        for sample_idx in range(1, len(channels[0]) if channels else 0):
            current_time = sample_idx * time_step_ps
            has_change = False
            
            # 检查是否有任何通道的值发生变化
            for i in range(len(channels)):
                value = channels[i][sample_idx]
                if prev_values[i] != value:
                    has_change = True
                    break
            
            # 如果有变化，写入时间戳和所有变化的值
            if has_change:
                f.write(f"#{current_time}\n")
                for i in range(len(channels)):
                    value = channels[i][sample_idx]
                    if prev_values[i] != value:
                        f.write(f"{value}{var_names[i]}\n")
                        prev_values[i] = value
    
    print(f"✓ VCD 文件已导出: {filename}")
    print(f"  提示: 可以在 PulseView 中打开此文件查看波形")


def export_csv_to_sr_via_sigrok_cli(csv_filename: str, sr_filename: str, sample_rate: float, num_channels: int) -> bool:
    """
    使用sigrok-cli将CSV文件转换为.sr文件
    sigrok-cli位于当前目录的sigrok-cli子目录下
    
    参数:
        csv_filename: CSV文件路径
        sr_filename: 输出.sr文件路径
        sample_rate: 采样率 (Hz)
        num_channels: 通道数量
    
    返回:
        True if成功, False if失败
    """
    import subprocess
    import os
    import platform
    
    # 确定sigrok-cli的路径（位于logic_analyzer目录下的sigrok-cli子目录）
    # 脚本在 examples/read_data.py，sigrok-cli在 logic_analyzer/sigrok-cli/
    script_dir = os.path.dirname(os.path.abspath(__file__))  # examples目录
    project_root = os.path.dirname(script_dir)  # logic_analyzer目录
    
    if platform.system() == 'Windows':
        sigrok_cli_path = os.path.join(project_root, 'sigrok-cli', 'sigrok-cli.exe')
    else:
        sigrok_cli_path = os.path.join(project_root, 'sigrok-cli', 'sigrok-cli')
    
    # 检查sigrok-cli是否存在
    if not os.path.exists(sigrok_cli_path):
        print(f"✗ 错误: 未找到sigrok-cli工具")
        print(f"  预期路径: {sigrok_cli_path}")
        print(f"  请确保sigrok-cli位于 logic_analyzer/sigrok-cli/ 目录下")
        # 尝试查找其他可能的位置
        alternative_paths = [
            os.path.join(script_dir, 'sigrok-cli', 'sigrok-cli.exe' if platform.system() == 'Windows' else 'sigrok-cli'),
            os.path.join(os.getcwd(), 'sigrok-cli', 'sigrok-cli.exe' if platform.system() == 'Windows' else 'sigrok-cli'),
        ]
        for alt_path in alternative_paths:
            if os.path.exists(alt_path):
                print(f"  找到替代路径: {alt_path}")
                sigrok_cli_path = alt_path
                break
        else:
            return False
    
    # 检查sigrok-cli是否可用
    try:
        result = subprocess.run([sigrok_cli_path, '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"✗ 错误: sigrok-cli无法运行")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"✗ 错误: sigrok-cli无法运行: {e}")
        return False
    
    # 构建逻辑列格式字符串（每列一个l）
    logic_format = ','.join(['l'] * num_channels)
    
    # 构建sigrok-cli命令
    # 方法3：忽略时间列，手动指定采样率
    cmd = [
        sigrok_cli_path,
        '-I', f'csv:header=yes:column_formats=-,{logic_format}:samplerate={int(sample_rate)}',
        '-i', csv_filename,
        '-o', sr_filename
    ]
    
    try:
        print(f"  正在使用sigrok-cli转换为.sr格式...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            if os.path.exists(sr_filename):
                file_size = os.path.getsize(sr_filename)
                print(f"✓ .sr文件已生成: {sr_filename} ({file_size/1024:.2f} KB)")
                return True
            else:
                print(f"✗ 错误: .sr文件未生成")
                return False
        else:
            print(f"✗ sigrok-cli转换失败:")
            if result.stderr:
                print(f"  {result.stderr}")
            if result.stdout:
                print(f"  {result.stdout}")
            return False
    except subprocess.TimeoutExpired:
        print(f"✗ 错误: sigrok-cli转换超时")
        return False
    except Exception as e:
        print(f"✗ 错误: {e}")
        return False


def export_to_csv(channels: List[List[int]], sample_rate: float, filename: str = 'logic_analyzer_data.csv', convert_to_sr: bool = True) -> None:
    """
    导出数据为 CSV 格式，符合 Sigrok CSV 格式规范
    参考: https://sigrok.org/wiki/File_format:Csv
    
    参数:
        channels: 通道数据列表（每个通道是一个0/1列表）
        sample_rate: 采样率 (Hz)
        filename: 输出文件名
    
    格式说明:
    - 使用时间戳列（第一列），sigrok可以自动计算采样率
    - 注释行以分号(;)开头（sigrok标准）
    - 支持header行，包含通道名称
    - 多列模式：每列一个bit（默认格式）
    """
    import csv
    
    samples = len(channels[0]) if channels else 0
    time_step = 1.0 / sample_rate  # 每个样本的时间（秒）
    
    # 根据sigrok CSV格式规范：
    # 1. 注释行以分号(;)开头（不是#）
    # 2. 第一列可以是时间戳（time列），sigrok可以自动计算采样率
    # 3. 支持header行，包含列名
    # 4. 多列模式：每列一个bit（默认格式）
    # 5. 时间戳格式：数字（秒），sigrok可以自动识别并计算采样率
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        # 写入注释行（sigrok标准：以分号开头，会被自动忽略）
        f.write(f"; CSV file generated by FPGA Logic Analyzer\n")
        f.write(f"; Sample Rate: {int(sample_rate)} Hz\n")
        f.write(f"; Channels: {len(channels)}, Samples: {samples}\n")
        f.write(f";\n")
        
        writer = csv.writer(f)
        
        # 写入表头（sigrok支持header行）
        # 第一列是时间戳（time），后续列是逻辑通道
        # 注意：如果使用column_formats='-,*l'，第一列会被忽略，需要手动指定samplerate
        header = ['time']  # 使用小写'time'，sigrok可以识别为时间戳列
        for i in range(len(channels)):
            header.append(f'CH{i}')
        writer.writerow(header)
        
        # 写入数据
        # 第一列是时间戳（秒），sigrok可以自动计算采样率
        # 后续列是逻辑数据（0或1）
        # 使用批量写入以提高性能
        batch_size = 10000
        for batch_start in range(0, samples, batch_size):
            batch_end = min(batch_start + batch_size, samples)
            rows = []
            for sample_idx in range(batch_start, batch_end):
                time_s = sample_idx * time_step  # 使用实际采样率计算时间
                # 时间格式：使用足够精度，sigrok可以自动识别并计算采样率
                row = [f"{time_s:.9f}"]
                for i in range(len(channels)):
                    row.append(channels[i][sample_idx])
                rows.append(row)
            writer.writerows(rows)
            
            if batch_end < samples:
                print(f"  已写入 {batch_end}/{samples} 行...", end='\r')
    
    
    print(f"✓ CSV 文件已导出: {filename}")
    print(f"  实际采样率: {int(sample_rate)} Hz", end="")
    if sample_rate >= 1e6:
        print(f" ({sample_rate/1e6:.6f} MHz)")
    elif sample_rate >= 1e3:
        print(f" ({sample_rate/1e3:.3f} kHz)")
    else:
        print()
    print(f"  通道数: {len(channels)}, 样本数: {samples}")
    
    # 自动转换为.sr格式
    if convert_to_sr:
        sr_filename = filename.replace('.csv', '.sr')
        success = export_csv_to_sr_via_sigrok_cli(filename, sr_filename, sample_rate, len(channels))
        
        if success:
            # 删除临时CSV文件和相关文档
            try:
                import os
                os.remove(filename)
                print(f"✓ 已删除临时CSV文件")
                # 删除info文件
                info_filename = filename.replace('.csv', '_info.txt')
                if os.path.exists(info_filename):
                    os.remove(info_filename)
            except Exception as e:
                pass  # 如果删除失败，忽略
            
            print(f"\n⭐ .sr文件已生成: {sr_filename}")
            print(f"  可以直接在PulseView中打开使用，采样率已自动包含")
        else:
            print(f"\n⚠ 警告: 无法自动转换为.sr格式（sigrok-cli未找到或转换失败）")
            print(f"  请确保sigrok-cli已安装并在PATH中")
            print(f"  或手动使用以下命令转换：")
            logic_format = ','.join(['l'] * len(channels))
            print(f"  sigrok-cli -I csv:header=yes:column_formats=-,{logic_format}:samplerate={int(sample_rate)} -i {filename} -o {sr_filename}")


def calculate_signal_frequency(channel_data: List[int], sample_rate: float = DEFAULT_SAMPLE_RATE) -> Optional[float]:
    """
    计算信号频率（通过检测边沿变化）
    
    参数:
        channel_data: 通道数据列表（0或1）
        sample_rate: 采样率
    
    返回:
        频率（Hz），如果无法计算则返回None
    """
    if len(channel_data) < 2:
        return None
    
    # 检测边沿（上升沿和下降沿）
    edges = []
    edge_types = []  # 记录边沿类型：1=上升沿，0=下降沿
    for i in range(1, len(channel_data)):
        if channel_data[i] != channel_data[i-1]:
            edges.append(i)
            edge_types.append(1 if channel_data[i] > channel_data[i-1] else 0)
    
    if len(edges) < 2:
        return None  # 没有足够的边沿
    
    # 计算平均周期（使用相同类型的边沿，例如两个上升沿之间）
    # 这样可以避免计算半个周期的问题
    periods = []
    
    # 方法1：使用上升沿计算周期（更准确）
    rising_edges = [edges[i] for i in range(len(edges)) if edge_types[i] == 1]
    if len(rising_edges) >= 2:
        for i in range(1, min(len(rising_edges), 20)):  # 最多使用20个上升沿
            period_samples = rising_edges[i] - rising_edges[i-1]
            periods.append(period_samples)
    
    # 方法2：如果没有足够的上升沿，使用下降沿
    if len(periods) < 2:
        falling_edges = [edges[i] for i in range(len(edges)) if edge_types[i] == 0]
        if len(falling_edges) >= 2:
            periods = []
            for i in range(1, min(len(falling_edges), 20)):  # 最多使用20个下降沿
                period_samples = falling_edges[i] - falling_edges[i-1]
                periods.append(period_samples)
    
    # 方法3：如果还是没有足够的边沿，使用所有边沿
    # 注意：相邻边沿如果是不同类型（上升沿和下降沿），间隔是半个周期，需要乘以2
    # 如果是相同类型，间隔就是一个完整周期，不需要乘以2
    if len(periods) < 2:
        periods = []
        for i in range(1, min(len(edges), 20)):  # 最多使用20个边沿
            if edge_types[i] != edge_types[i-1]:
                # 相邻边沿类型不同（上升沿和下降沿），间隔是半个周期
                period_samples = (edges[i] - edges[i-1]) * 2
            else:
                # 相邻边沿类型相同，间隔是一个完整周期
                period_samples = edges[i] - edges[i-1]
            periods.append(period_samples)
    
    if len(periods) == 0:
        return None
    
    # 计算平均周期（样本数）
    avg_period_samples = sum(periods) / len(periods)
    
    # 转换为时间（秒）
    period_time = avg_period_samples / sample_rate
    
    # 计算频率
    frequency = 1.0 / period_time if period_time > 0 else None
    
    return frequency


def calculate_duty_cycle(channel_data: List[int]) -> Optional[float]:
    """
    计算占空比
    
    参数:
        channel_data: 通道数据列表（0或1）
    
    返回:
        占空比（0-100），如果无法计算则返回None
    """
    if len(channel_data) == 0:
        return None
    
    high_count = sum(channel_data)
    duty_cycle = (high_count / len(channel_data)) * 100
    
    return duty_cycle


def analyze_data(channels: List[List[int]], sample_rate: float = SAMPLE_RATE) -> None:
    """分析数据并显示统计信息"""
    samples = len(channels[0])
    if samples == 0:
        print("⚠ 没有数据可分析")
        return
    
    # 计算采样参数
    sample_period = 1.0 / sample_rate  # 每个样本的周期（秒）
    total_duration = samples / sample_rate  # 总采样时长（秒）
    
    print("\n=== 采样参数 ===")
    if sample_rate >= 1e6:
        print(f"采样率: {sample_rate/1e6:.2f} MHz")
    else:
        print(f"采样率: {sample_rate/1e3:.2f} kHz")
    print(f"样本周期: {sample_period*1e9:.3f} ns ({sample_period*1e6:.6f} μs)")
    print(f"采样点数: {samples:,}")
    if total_duration >= 1:
        print(f"采样时长: {total_duration:.3f} s ({total_duration*1e3:.3f} ms)")
    elif total_duration >= 1e-3:
        print(f"采样时长: {total_duration*1e3:.3f} ms ({total_duration*1e6:.3f} μs)")
    else:
        print(f"采样时长: {total_duration*1e6:.3f} μs ({total_duration*1e9:.3f} ns)")
    
    print("\n=== 通道分析 ===")
    for ch in range(CHANNELS):
        channel_data = channels[ch]
        high_count = sum(channel_data)
        low_count = samples - high_count
        high_percent = high_count / samples * 100 if samples > 0 else 0
        
        # 检查通道是否有变化（用于判断是否有信号）
        has_transitions = False
        if len(channel_data) > 1:
            for i in range(1, len(channel_data)):
                if channel_data[i] != channel_data[i-1]:
                    has_transitions = True
                    break
        
        # 计算信号频率
        frequency = calculate_signal_frequency(channel_data, sample_rate)
        
        # 计算占空比
        duty_cycle = calculate_duty_cycle(channel_data)
        
        print(f"\nCH{ch}:")
        print(f"  高电平: {high_count:,} ({high_percent:.1f}%)")
        print(f"  低电平: {low_count:,} ({100-high_percent:.1f}%)")
        
        # 特别检查CH2
        if ch == 2:
            # 显示前20个样本的原始值用于调试
            preview_samples = min(20, len(channel_data))
            preview_str = ' '.join([str(b) for b in channel_data[:preview_samples]])
            print(f"  前{preview_samples}个样本: {preview_str}")
            # 检查是否有变化
            if not has_transitions:
                print(f"  ⚠ 警告: CH2没有检测到信号变化（可能引脚未连接或信号恒定）")
                print(f"  提示: 如果CH2连接到信号源，请检查：")
                print(f"    1. 引脚27是否正确连接")
                print(f"    2. 信号源是否有足够的驱动能力（可能需要去除PULL_MODE=UP）")
                print(f"    3. 信号电平是否在0-3.3V范围内")
        
        if duty_cycle is not None:
            print(f"  占空比: {duty_cycle:.1f}%")
        
        if frequency is not None:
            print(f"  信号频率: {frequency:,.2f} Hz ({frequency/1000:.3f} kHz)")
            if frequency >= 1e6:
                print(f"              {frequency/1e6:.3f} MHz")
            
            # 计算信号周期
            signal_period = 1.0 / frequency if frequency > 0 else 0
            if signal_period >= 1e-3:
                print(f"  信号周期: {signal_period*1000:.3f} ms")
            elif signal_period >= 1e-6:
                print(f"  信号周期: {signal_period*1e6:.3f} μs")
            else:
                print(f"  信号周期: {signal_period*1e9:.3f} ns")
        else:
            if not has_transitions:
                print(f"  信号频率: 无法计算（信号为恒定电平）")
            else:
                print(f"  信号频率: 无法计算（无足够边沿）")


def main():
    """主函数"""
    # 正常模式：从FPGA读取数据
    if len(sys.argv) < 2:
        print("用法: python read_data.py <COM端口> [选项]")
        print("示例: python read_data.py COM3")
        print("\n选项:")
        print("  --no-plot        不显示波形图")
        print("  --save           保存原始数据到文件 (.bin)")
        print("  --export-csv     导出为 .sr 格式（通过CSV自动转换，需要sigrok-cli）")
        print("  --csv-only       仅导出CSV文件，不转换为.sr格式（需配合--export-csv使用）")
        print("  --trigger <模式>     设置触发模式（在采样前）")
        print("                       可选值: immediate(立即), rising(上升沿), falling(下降沿),")
        print("                              both(双边沿), pattern(模式), high(高电平), low(低电平)")
        print("                       默认: immediate（立即开始采样）")
        print("  --trigger-mask <掩码>  触发通道掩码（十六进制，如0xFF表示所有通道）")
        print("                       默认: 0xFF（所有通道）")
        print("                       示例: 0x01（仅CH0）, 0x03（CH0和CH1）")
        print("  --trigger-pattern <模式>  触发模式值（十六进制，用于模式触发）")
        print("                       默认: 0x00")
        print("                       示例: 0x55（01010101）, 0xAA（10101010）")
        print("  --pre-trigger <数量>   预触发样本数（在触发前先采样指定数量的样本）")
        print("                       默认: 0（无预触发）")
        print("                       注意: 当前FPGA实现可能不支持预触发功能")
        print("  --freq <Hz>          设置频率输出（在采样前）")
        print("  --duty <值>          设置占空比（在采样前，需要先设置频率）")
        print("                       格式: 50, 50%, 0.5 (范围: 0-100%)")
        print("  --stop               手动停止采样（否则等待缓冲区满）")
        print("  --sample-rate <Hz>   设置FPGA硬件采样率（分频PLL时钟）")
        print("                       例如: --sample-rate 1000000 (1MHz)")
        print("                       预设值: 27M, 13.5M, 9M, 6.75M, 5.4M, 1M, 500k, 100k, 50k, 10k, 1k")
        print("                       例如: --sample-rate 1M 或 --sample-rate 100k")
        print("                       默认: 100kHz（如果不指定）")
        print("                       注意: 系统时钟为27MHz，此参数用于分频")
        print("  --display-rate <Hz>  指定显示用采样率（用于计算和频率输出）")
        print("                       例如: --display-rate 1k 或 --display-rate 1000")
        print("  --duty <值>          设置占空比（使用display-rate作为频率）")
        print("                       格式: 0.8, 80, 80% (范围: 0-100%)")
        print("  --export-csv         导出为CSV文件")
        print("  --test-data          在采样时持续发送0~255测试数据到FPGA")
        print("                       提示: 如果CH1连接到UART的RX引脚，可以抓取这些测试数据")
        sys.exit(1)
    
    port = sys.argv[1]
    export_csv = '--export-csv' in sys.argv
    send_test_data = '--test-data' in sys.argv  # 是否发送测试数据
    
    # 解析采样率参数（FPGA硬件采样率）
    fpga_sample_rate = None
    if '--sample-rate' in sys.argv:
        sample_rate_idx = sys.argv.index('--sample-rate')
        if sample_rate_idx + 1 < len(sys.argv):
            try:
                # 支持预设值和数字
                fpga_sample_rate = parse_sample_rate(sys.argv[sample_rate_idx + 1])
                if fpga_sample_rate <= 0 or fpga_sample_rate > SAMPLE_RATE:
                    print(f"✗ 错误: 采样率必须在 0 到 {SAMPLE_RATE/1e6:.2f} MHz 之间")
                    sys.exit(1)
            except (ValueError, KeyError) as e:
                print("✗ 错误: --sample-rate 参数格式不正确")
                print("  支持格式: 数字 (如 1000000) 或预设值 (如 1M, 100k)")
                print("  预设值: 27M, 13.5M, 1M, 500k, 100k, 50k, 10k, 1k")
                sys.exit(1)
        else:
            print("✗ 错误: --sample-rate 参数需要指定频率值")
            sys.exit(1)
    
    # 解析显示用采样率参数（仅用于计算和显示）
    # 默认使用FPGA的默认采样率（100kHz），如果设置了FPGA采样率则使用实际值
    display_sample_rate = DEFAULT_SAMPLE_RATE  # 默认100kHz（与FPGA一致）
    if '--display-rate' in sys.argv:
        display_rate_idx = sys.argv.index('--display-rate')
        if display_rate_idx + 1 < len(sys.argv):
            try:
                # 支持预设值和数字格式（与--sample-rate一致）
                display_sample_rate = parse_sample_rate(sys.argv[display_rate_idx + 1])
                if display_sample_rate <= 0:
                    print("✗ 错误: 显示采样率必须大于0")
                    sys.exit(1)
                if display_sample_rate >= 1e6:
                    print(f"✓ 使用自定义显示采样率: {display_sample_rate/1e6:.2f} MHz (仅用于计算和显示)")
                else:
                    print(f"✓ 使用自定义显示采样率: {display_sample_rate/1e3:.2f} kHz (仅用于计算和显示)")
            except (ValueError, KeyError) as e:
                print("✗ 错误: --display-rate 参数格式不正确")
                print("  支持格式: 数字 (如 500000) 或预设值 (如 500k, 1M)")
                print("  预设值: 27M, 13.5M, 1M, 500k, 100k, 50k, 10k, 1k")
                sys.exit(1)
        else:
            print("✗ 错误: --display-rate 参数需要指定频率值")
            sys.exit(1)
    
    # 解析占空比参数（使用display-rate作为频率）
    target_duty = None
    if '--duty' in sys.argv:
        duty_arg_idx = sys.argv.index('--duty')
        if duty_arg_idx + 1 < len(sys.argv):
            duty_str = sys.argv[duty_arg_idx + 1]
            target_duty = parse_duty_arg(duty_str)
            if target_duty is None:
                print(f"✗ 错误: --duty 参数 '{duty_str}' 格式不正确")
                print("  支持格式: 0.8, 80, 80% (范围: 0-100%)")
                sys.exit(1)
        else:
            print("✗ 错误: --duty 参数需要指定占空比值")
            sys.exit(1)
    
    # 打开串口
    ser = open_serial(port)
    time.sleep(0.5)  # 等待串口稳定
    
    try:
        # 等待启动消息
        wait_for_startup(ser, timeout=2.0)
        
        # 清空接收缓冲区
        ser.reset_input_buffer()
        
        # 设置频率输出和占空比（使用display-rate作为频率）
        if target_duty is not None:
            # 检查是否设置了display-rate
            if '--display-rate' not in sys.argv:
                print("✗ 错误: 设置占空比需要先设置 --display-rate（用作频率）")
                sys.exit(1)
            
            # 使用display_rate作为频率
            target_freq = display_sample_rate
            print(f"\n设置频率输出: {target_freq} Hz (使用display-rate)")
            actual_freq = set_frequency(ser, target_freq)
            time.sleep(0.1)
            
            print(f"\n设置占空比: {target_duty*100:.2f}%")
            actual_duty, duty_high_cycles = set_duty_cycle(ser, actual_freq, target_duty)
            period_cycles = int(27_000_000 / actual_freq)
            print(f"✓ 占空比已设置: {target_duty*100:.2f}% → {actual_duty*100:.2f}%")
            print(f"  高电平时间: {duty_high_cycles} 个时钟周期 ({duty_high_cycles/27_000_000*1e6:.2f} μs)")
            print(f"  完整周期: {period_cycles} 个时钟周期 ({period_cycles/27_000_000*1e6:.2f} μs)")
            time.sleep(0.1)
        
        # 可选：设置FPGA采样率
        actual_fpga_rate = None  # 保存实际的FPGA硬件采样率，用于CSV导出
        if fpga_sample_rate is not None:
            if fpga_sample_rate >= 1e6:
                print(f"\n设置FPGA采样率: {fpga_sample_rate/1e6:.2f} MHz")
            else:
                print(f"\n设置FPGA采样率: {fpga_sample_rate/1e3:.2f} kHz")
            actual_fpga_rate = set_sample_rate(ser, fpga_sample_rate)
            display_sample_rate = actual_fpga_rate  # 使用实际采样率作为显示采样率（如果未指定display-rate）
            time.sleep(0.15)  # 等待采样率更新完成并稳定（150ms足够）
        else:
            # 如果没有设置采样率，使用FPGA默认值（100kHz）
            # 注意：FPGA复位后默认采样率是100kHz，我们需要使用这个值
            actual_fpga_rate = DEFAULT_SAMPLE_RATE
            display_sample_rate = DEFAULT_SAMPLE_RATE
            print(f"\n使用FPGA默认采样率: {display_sample_rate/1e3:.2f} kHz")
            print("提示: 如需修改采样率，使用 --sample-rate 参数")
        
        # 配置触发（默认立即触发）
        configure_trigger(ser, 0, 0, 0)  # 立即触发：不使用触发
        time.sleep(0.1)  # 等待触发配置完成
        
        # 开始采样
        print("\n" + "="*50)
        # 如果设置了采样率，额外等待确保采样率稳定
        if fpga_sample_rate is not None:
            time.sleep(0.05)  # 额外等待50ms，确保采样率稳定
        
        # 发送开始采样命令
        start_sampling(ser)
        time.sleep(0.1)  # 等待采样启动
        
        # 如果启用了测试数据发送，启动测试数据发送线程
        test_data_stop_flag = None
        test_data_thread = None
        if send_test_data:
            test_data_stop_flag = threading.Event()
            test_data_thread = threading.Thread(
                target=send_test_data_continuous,
                args=(ser, test_data_stop_flag),
                daemon=True
            )
            test_data_thread.start()
            print("✓ 测试数据发送线程已启动")
            time.sleep(0.2)  # 等待线程启动
        
        # 等待采样完成（缓冲区满时自动停止）
        print("\n等待采样完成（缓冲区满时自动停止）...")
        # 估算采样时间：使用实际FPGA采样率
        actual_sample_rate = actual_fpga_rate if actual_fpga_rate is not None else DEFAULT_SAMPLE_RATE
        estimated_time = (BUFFER_SIZE / actual_sample_rate) * 2.0  # 2.0倍安全系数，确保有足够时间
        if actual_sample_rate >= 1e6:
            print(f"预计采样时间: {estimated_time*1000:.2f} ms (基于FPGA采样率 {actual_sample_rate/1e6:.2f} MHz)")
        else:
            print(f"预计采样时间: {estimated_time*1000:.2f} ms (基于FPGA采样率 {actual_sample_rate/1e3:.2f} kHz)")
        print(f"  缓冲区大小: {BUFFER_SIZE} 字节")
        print(f"  预计样本数: {BUFFER_SIZE} 个")
        
        time.sleep(estimated_time + 0.5)  # 等待采样完成，额外增加0.5秒安全时间
        
        # 停止测试数据发送（如果启用）
        if send_test_data and test_data_stop_flag is not None:
            print("\n停止测试数据发送...")
            test_data_stop_flag.set()
            if test_data_thread is not None:
                test_data_thread.join(timeout=1.0)  # 等待线程结束，最多1秒
            print("✓ 测试数据发送已停止")
        
        # 自动接收数据（采样完成后自动发送）
        # 增加超时时间到60秒，给低采样率足够的时间
        data = wait_for_data(ser, expected_size=BUFFER_SIZE, timeout=60.0)
        
        if len(data) == 0:
            print("✗ 未收到任何数据")
            print("提示: 检查信号连接和采样设置")
            return
        
        # 解析通道数据
        print("\n解析通道数据...")
        channels = parse_channels(data)
        
        # 调试：显示前几个字节的原始数据，特别检查CH2
        if len(data) > 0:
            print(f"  前10个字节的原始数据（十六进制）: {[hex(b) for b in data[:10]]}")
            print(f"  前10个字节的原始数据（二进制）: {[bin(b)[2:].zfill(8) for b in data[:10]]}")
            # 检查CH2（bit 2）的值
            ch2_bits = [(b >> 2) & 1 for b in data[:10]]
            print(f"  CH2前10个样本: {ch2_bits}")
        
        # 分析数据（使用显示采样率）
        analyze_data(channels, sample_rate=display_sample_rate)
        
        # 导出为 CSV 格式（自动转换为.sr格式）
        # CSV导出使用实际的FPGA硬件采样率计算时间，而不是display-rate
        if export_csv:
            print("\n导出 CSV 格式...")
            # 使用实际的FPGA采样率（--sample-rate指定的值）来计算时间
            csv_sample_rate = actual_fpga_rate if actual_fpga_rate is not None else DEFAULT_SAMPLE_RATE
            if csv_sample_rate != display_sample_rate:
                print(f"  注意: 使用FPGA硬件采样率: {int(csv_sample_rate)} Hz (而非显示采样率: {int(display_sample_rate)} Hz)")
            # 导出CSV格式并自动转换为.sr格式
            export_to_csv(channels, csv_sample_rate, convert_to_sr=True)
        
        # 不显示波形图（默认）
        
        print("\n✓ 完成！")
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ser.close()
        print("串口已关闭")


if __name__ == '__main__':
    main()
