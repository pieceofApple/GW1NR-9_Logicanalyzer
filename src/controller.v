`timescale 1ns / 1ps
// 主控制器模块
// 功能: 协调各个模块，实现状态机控制，使用LED指示状态
module controller(
    input clk,
    input resetn,
    
    // UART 接口
    input [7:0] uart_rx_data,
    input uart_rx_valid,
    output [7:0] uart_tx_data,
    output uart_tx_start,
    input uart_tx_done,
    
    // 采样器接口
    output sampler_enable,
    
    // 触发接口
    input trigger_detected,
    output [7:0] trigger_mask,
    output [1:0] trigger_type,
    output [7:0] trigger_pattern,
    
    // 缓冲接口
    output buffer_write_en,
    output buffer_read_en,
    output buffer_clear,          // 清除缓冲区
    input buffer_full,
    input buffer_empty,
    input [15:0] buffer_sample_count,
    input [7:0] buffer_data_out,  // 从缓冲区读取的数据
    
    // 频率生成器接口
    output [31:0] freq_divider,
    output freq_update,
    output [31:0] duty_cycle_high,  // 占空比：高电平持续时间
    output duty_update,              // 占空比更新使能
    
    // 采样率分频器接口
    output [31:0] sample_rate_divider,
    output sample_rate_update,
    
    // 状态输出（用于LED）
    output [2:0] state_out
);

// 状态定义
localparam IDLE      = 3'b000;
localparam CONFIG    = 3'b001;
localparam ARM       = 3'b010;
localparam SAMPLING  = 3'b011;
localparam READY     = 3'b100;
localparam TRANSMIT  = 3'b101;
localparam SET_FREQ   = 3'b110;  // 设置频率状态
localparam SET_SAMPLE_RATE = 3'b111;  // 设置采样率状态
// 注意：状态只有3位，无法添加新状态，使用SET_FREQ状态处理占空比设置

// 命令定义
localparam CMD_START     = 8'h01;
localparam CMD_STOP      = 8'h02;
localparam CMD_TRIGGER   = 8'h04;  // 触发配置命令（进入CONFIG状态）
localparam CMD_CONFIG    = 8'h05;  // 触发配置数据（进入CONFIG状态）
localparam CMD_SET_FREQ  = 8'h06;  // 设置频率输出
localparam CMD_SET_SAMPLE_RATE = 8'h07;  // 设置采样率
localparam CMD_SET_DUTY  = 8'h08;  // 设置占空比

reg [2:0] state;
reg [7:0] trigger_mask_reg;
reg [1:0] trigger_type_reg;
reg [7:0] trigger_pattern_reg;
reg [15:0] transmit_count;
reg [15:0] transmit_total;

// 频率设置相关
reg [31:0] freq_divider_reg;
reg [2:0] freq_byte_count;  // 接收字节计数 (0-3)
reg freq_update_reg;

// 占空比设置相关
reg [31:0] duty_cycle_high_reg;
reg [2:0] duty_byte_count;  // 接收字节计数 (0-3)
reg duty_update_reg;
reg setting_duty;  // 标志：正在设置占空比（而不是频率）

// 采样率设置相关
reg [31:0] sample_rate_divider_reg;
reg [2:0] sample_rate_byte_count;  // 接收字节计数 (0-3)
reg sample_rate_update_reg;

// 状态输出（用于LED）
assign state_out = state;

// 采样使能
assign sampler_enable = (state == SAMPLING);

// 触发配置
assign trigger_mask = trigger_mask_reg;
assign trigger_type = trigger_type_reg;
assign trigger_pattern = trigger_pattern_reg;

// 缓冲控制
assign buffer_write_en = (state == SAMPLING) && sampler_enable && ~buffer_full;
// 读取使能：在TRANSMIT状态且满足读取条件时
assign buffer_read_en = (state == TRANSMIT) && (
    (uart_tx_done && transmit_count < transmit_total) ||  // 发送完成后读取下一个
    (transmit_count == 16'd0 && ~buffer_empty)            // 首次进入TRANSMIT时立即读取
);
// 清除缓冲区：在ARM状态时清除，准备新采样
assign buffer_clear = (state == ARM);

// 频率生成器控制
assign freq_divider = freq_divider_reg;
assign freq_update = freq_update_reg;
assign duty_cycle_high = duty_cycle_high_reg;
assign duty_update = duty_update_reg;

// 采样率分频器控制
assign sample_rate_divider = sample_rate_divider_reg;
assign sample_rate_update = sample_rate_update_reg;

// UART 发送控制
reg [7:0] uart_tx_data_reg;
reg uart_tx_start_reg;
assign uart_tx_data = uart_tx_data_reg;
assign uart_tx_start = uart_tx_start_reg;

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        state <= IDLE;
        trigger_mask_reg <= 8'hFF;      // 默认所有通道
        trigger_type_reg <= 2'b00;      // 默认上升沿触发
        trigger_pattern_reg <= 8'h00;
        transmit_count <= 16'd0;
        transmit_total <= 16'd0;
        uart_tx_data_reg <= 8'd0;
        uart_tx_start_reg <= 1'b0;
        freq_divider_reg <= 32'd1350;  // 初始频率 10kHz
        freq_byte_count <= 3'd0;
        freq_update_reg <= 1'b0;
        duty_cycle_high_reg <= 32'd1350;  // 初始占空比50%（高电平时间 = 分频比）
        duty_byte_count <= 3'd0;
        duty_update_reg <= 1'b0;
        setting_duty <= 1'b0;
        sample_rate_divider_reg <= 32'd270;  // 默认100kHz采样率 (27MHz / 270 = 100kHz)
        sample_rate_byte_count <= 3'd0;
        sample_rate_update_reg <= 1'b0;
    end else begin
        uart_tx_start_reg <= 1'b0;
        freq_update_reg <= 1'b0;
        duty_update_reg <= 1'b0;
        sample_rate_update_reg <= 1'b0;  // 确保sample_rate_update只持续一个周期
        
        case (state)
            IDLE: begin
                if (uart_rx_valid) begin
                    case (uart_rx_data)
                        CMD_START: begin
                            state <= ARM;
                        end
                        CMD_TRIGGER: begin
                            state <= CONFIG;
                        end
                        CMD_CONFIG: begin
                            state <= CONFIG;
                        end
                        CMD_SET_FREQ: begin
                            state <= SET_FREQ;
                            freq_byte_count <= 3'd0;
                            setting_duty <= 1'b0;  // 设置频率
                        end
                        CMD_SET_DUTY: begin
                            state <= SET_FREQ;  // 复用SET_FREQ状态
                            duty_byte_count <= 3'd0;
                            setting_duty <= 1'b1;  // 标志：设置占空比
                        end
                        CMD_SET_SAMPLE_RATE: begin
                            state <= SET_SAMPLE_RATE;
                            sample_rate_byte_count <= 3'd0;
                        end
                        default: begin
                            // 忽略未知命令
                        end
                    endcase
                end
            end
            
            SET_FREQ: begin
                // 接收4个字节的频率分频比或占空比 (小端序)
                if (uart_rx_valid) begin
                    if (setting_duty) begin
                        // 设置占空比
                        case (duty_byte_count)
                            3'd0: begin
                                duty_cycle_high_reg[7:0] <= uart_rx_data;
                                duty_byte_count <= 3'd1;
                            end
                            3'd1: begin
                                duty_cycle_high_reg[15:8] <= uart_rx_data;
                                duty_byte_count <= 3'd2;
                            end
                            3'd2: begin
                                duty_cycle_high_reg[23:16] <= uart_rx_data;
                                duty_byte_count <= 3'd3;
                            end
                            3'd3: begin
                                duty_cycle_high_reg[31:24] <= uart_rx_data;
                                duty_update_reg <= 1'b1;  // 更新占空比
                                state <= IDLE;
                                duty_byte_count <= 3'd0;
                                setting_duty <= 1'b0;
                            end
                        endcase
                    end else begin
                        // 设置频率
                        case (freq_byte_count)
                            3'd0: begin
                                freq_divider_reg[7:0] <= uart_rx_data;
                                freq_byte_count <= 3'd1;
                            end
                            3'd1: begin
                                freq_divider_reg[15:8] <= uart_rx_data;
                                freq_byte_count <= 3'd2;
                            end
                            3'd2: begin
                                freq_divider_reg[23:16] <= uart_rx_data;
                                freq_byte_count <= 3'd3;
                            end
                            3'd3: begin
                                freq_divider_reg[31:24] <= uart_rx_data;
                                freq_update_reg <= 1'b1;  // 更新频率
                                state <= IDLE;
                                freq_byte_count <= 3'd0;
                            end
                        endcase
                    end
                end
            end
            
            SET_SAMPLE_RATE: begin
                // 接收4个字节的采样率分频比 (小端序)
                if (uart_rx_valid) begin
                    case (sample_rate_byte_count)
                        3'd0: begin
                            sample_rate_divider_reg[7:0] <= uart_rx_data;
                            sample_rate_byte_count <= 3'd1;
                        end
                        3'd1: begin
                            sample_rate_divider_reg[15:8] <= uart_rx_data;
                            sample_rate_byte_count <= 3'd2;
                        end
                        3'd2: begin
                            sample_rate_divider_reg[23:16] <= uart_rx_data;
                            sample_rate_byte_count <= 3'd3;
                        end
                        3'd3: begin
                            sample_rate_divider_reg[31:24] <= uart_rx_data;
                            sample_rate_update_reg <= 1'b1;  // 更新采样率
                            state <= IDLE;
                            sample_rate_byte_count <= 3'd0;
                        end
                    endcase
                end
            end
            
            CONFIG: begin
                // 等待接收配置参数
                // 简化版本：直接返回 IDLE
                state <= IDLE;
            end
            
            ARM: begin
                // 等待触发，同时可以接收频率和采样率设置命令
                // 重置传输计数，准备新的采样
                transmit_count <= 16'd0;
                transmit_total <= 16'd0;
                
                if (uart_rx_valid) begin
                    if (uart_rx_data == CMD_SET_FREQ) begin
                        state <= SET_FREQ;
                        freq_byte_count <= 3'd0;
                        setting_duty <= 1'b0;
                    end else if (uart_rx_data == CMD_SET_DUTY) begin
                        state <= SET_FREQ;
                        duty_byte_count <= 3'd0;
                        setting_duty <= 1'b1;
                    end else if (uart_rx_data == CMD_SET_SAMPLE_RATE) begin
                        state <= SET_SAMPLE_RATE;
                        sample_rate_byte_count <= 3'd0;
                    end else begin
                        // 立即开始采样（不等待触发，简化设计）
                        state <= SAMPLING;
                    end
                end else begin
                    // 检查触发条件（即使不使用触发，也确保trigger_detected被使用，防止模块被优化）
                    // 如果trigger_type_reg为0（立即触发）或trigger_mask为0，则立即开始采样
                    if (trigger_type_reg == 2'b00 || trigger_mask_reg == 8'h00 || trigger_detected) begin
                        state <= SAMPLING;
                    end
                    // 否则等待触发条件满足
                end
            end
            
            SAMPLING: begin
                // 持续采样直到缓冲区满或收到停止命令
                // 在采样过程中也可以接收频率、占空比和采样率设置命令
                if (uart_rx_valid) begin
                    if (uart_rx_data == CMD_SET_FREQ) begin
                        state <= SET_FREQ;
                        freq_byte_count <= 3'd0;
                        setting_duty <= 1'b0;
                    end else if (uart_rx_data == CMD_SET_DUTY) begin
                        state <= SET_FREQ;
                        duty_byte_count <= 3'd0;
                        setting_duty <= 1'b1;
                    end else if (uart_rx_data == CMD_SET_SAMPLE_RATE) begin
                        state <= SET_SAMPLE_RATE;
                        sample_rate_byte_count <= 3'd0;
                    end else if (uart_rx_data == CMD_STOP) begin
                        state <= READY;
                        transmit_total <= buffer_sample_count;
                    end
                end else if (buffer_full) begin
                    state <= READY;
                    transmit_total <= buffer_sample_count;
                end
            end
            
            READY: begin
                // 准备传输数据
                // 采样完成后自动开始传输
                transmit_count <= 16'd0;
                state <= TRANSMIT;
            end
            
            TRANSMIT: begin
                // 传输数据
                if (transmit_count == 16'd0 && ~buffer_empty) begin
                    // 首次进入TRANSMIT，立即读取第一个字节
                    uart_tx_data_reg <= buffer_data_out;
                    transmit_count <= transmit_count + 1'b1;
                    uart_tx_start_reg <= 1'b1;
                end else if (uart_tx_done) begin
                    if (transmit_count < transmit_total) begin
                        // 从缓冲区读取下一个字节
                        uart_tx_data_reg <= buffer_data_out;
                        transmit_count <= transmit_count + 1'b1;
                        uart_tx_start_reg <= 1'b1;
                    end else begin
                        // 传输完成，重置相关寄存器
                        state <= IDLE;
                        transmit_count <= 16'd0;
                        transmit_total <= 16'd0;
                    end
                end
            end
            
            default: begin
                state <= IDLE;
            end
        endcase
    end
end

endmodule
