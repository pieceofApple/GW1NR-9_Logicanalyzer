`timescale 1ns / 1ps
// 逻辑分析仪顶层模块
// TANG NANO 9K FPGA
module top(
    input clk,              // 27MHz 系统时钟
    input resetn,           // 复位信号，低有效
    
    // 逻辑分析仪输入通道 (8通道)
    input [7:0] la_data_in,
    
    // UART 接口
    output uart_tx,         // UART 发送 (板载 Type-C, 引脚17)
    input uart_rx,          // UART 接收 (板载 Type-C, 引脚18)
    output uart_tx_ext,     // UART 发送 (外部引出, 3.3V)
    output uart_rx_ext,      // UART 接收同步输出 (外部引出, 3.3V, 与uart_rx同步)
    
    // 状态指示 LED (可选)
    output [2:0] led_state,  // 状态指示
    
    // 频率输出
    output freq_out         // 可调频率输出
);

// 内部信号
wire [7:0] sampled_data;
wire sampler_valid;
wire sampler_enable;

wire trigger_detected;
wire [7:0] trigger_mask;
wire [1:0] trigger_type;
wire [7:0] trigger_pattern;

wire buffer_write_en;
wire buffer_read_en;
wire buffer_clear;
wire [7:0] buffer_data_out;
wire [15:0] buffer_write_addr;
wire [15:0] buffer_read_addr;
wire buffer_full;
wire buffer_empty;
wire [15:0] buffer_sample_count;

wire [7:0] uart_rx_data;
wire uart_rx_valid;
wire [7:0] uart_tx_data;
wire uart_tx_start;
wire uart_tx_done;

wire [2:0] controller_state;

// 启动发送模块接口
wire [7:0] startup_tx_data;
wire startup_tx_start;
wire startup_tx_done;
wire startup_done;

// 频率生成器接口
wire [31:0] freq_divider;
wire freq_update;
wire [31:0] duty_cycle_high;
wire duty_update;

// 采样率分频器接口
wire [31:0] sample_rate_divider;
wire sample_rate_update;
wire sample_clk_en;  // 采样时钟使能信号

// 采样率分频器模块（使用系统时钟27MHz）
sample_rate_divider u_sample_rate_divider(
    .clk(clk),        // 使用27MHz系统时钟
    .resetn(resetn),
    .divider(sample_rate_divider),
    .update(sample_rate_update),
    .sample_clk_en(sample_clk_en)
);

// 上一周期的数据（用于边沿检测）
reg [7:0] data_prev;

// 将uart_rx通过同步器输出到uart_rx_ext（引脚34）
// uart_rx_ext是输出引脚，输出uart_rx的同步信号，可用于示波器测量和逻辑分析仪采样
// 使用同步器确保信号稳定，防止被优化
reg uart_rx_ext_reg;
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        uart_rx_ext_reg <= 1'b1;
    end else begin
        uart_rx_ext_reg <= uart_rx;
    end
end
assign uart_rx_ext = uart_rx_ext_reg;

// 采样器模块（使用系统时钟和采样使能信号）
sampler u_sampler(
    .clk(clk),  // 使用27MHz系统时钟
    .resetn(resetn),
    .data_in(la_data_in),  // 使用原始输入，CH3保持独立
    .enable(sampler_enable && sample_clk_en),  // 采样使能且采样时钟使能
    .data_out(sampled_data),
    .valid(sampler_valid)
);

// 保存上一周期的数据
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        data_prev <= 8'b0;
    end else begin
        if (sampler_valid) begin
            data_prev <= sampled_data;
        end
    end
end

// 触发模块
trigger u_trigger(
    .clk(clk),  // 使用系统时钟
    .resetn(resetn),
    .data(sampled_data),
    .data_prev(data_prev),
    .trigger_mask(trigger_mask),
    .trigger_type(trigger_type),
    .trigger_pattern(trigger_pattern),
    .trigger_detected(trigger_detected)
);

// BRAM 缓冲模块
// 写入使能：必须与sample_clk_en同步，确保只在有效采样时写入
wire buffer_write_en_sync;
assign buffer_write_en_sync = buffer_write_en && sample_clk_en;

bram_buffer u_buffer(
    .clk(clk),  // 使用27MHz系统时钟作为BRAM时钟
    .resetn(resetn),
    .data_in(sampled_data),
    .write_en(buffer_write_en_sync),  // 使用同步后的写入使能
    .read_en(buffer_read_en),         // 直接使用读取使能
    .clear(buffer_clear),             // 清除缓冲区
    .data_out(buffer_data_out),
    .write_addr(buffer_write_addr),
    .read_addr(buffer_read_addr),
    .full(buffer_full),
    .empty(buffer_empty),
    .sample_count(buffer_sample_count)
);

// UART 接收模块
uart_rx u_uart_rx(
    .clk(clk),
    .resetn(resetn),
    .uart_rx(uart_rx),
    .data_out(uart_rx_data),
    .data_valid(uart_rx_valid)
);

// 启动发送模块（复位后发送"start"）
startup_tx u_startup_tx(
    .clk(clk),
    .resetn(resetn),
    .tx_data(startup_tx_data),
    .tx_start(startup_tx_start),
    .tx_done(startup_tx_done),
    .startup_done(startup_done)
);

// UART 发送模块（多路复用：启动发送优先，完成后使用控制器发送）
wire [7:0] uart_tx_actual_data;  // 修复：应该是8位数据总线
wire uart_tx_actual_start;
wire uart_tx_actual_done;

// 多路复用逻辑：启动发送未完成时使用启动发送，完成后使用控制器发送
assign uart_tx_actual_data = startup_done ? uart_tx_data : startup_tx_data;
assign uart_tx_actual_start = startup_done ? uart_tx_start : startup_tx_start;
assign startup_tx_done = ~startup_done ? uart_tx_actual_done : 1'b0;
assign uart_tx_done = startup_done ? uart_tx_actual_done : 1'b0;

// 板载 UART (Type-C, 引脚17/18) - 保留用于板载USB转串口
uart_tx u_uart_tx(
    .clk(clk),
    .resetn(resetn),
    .data_in(uart_tx_actual_data),
    .tx_start(uart_tx_actual_start),
    .tx_done(uart_tx_actual_done),
    .uart_tx(uart_tx)
);

// 外部 UART (可引出测量, 引脚33/34) - 与板载UART并行输出相同数据
uart_tx u_uart_tx_ext(
    .clk(clk),
    .resetn(resetn),
    .data_in(uart_tx_actual_data),
    .tx_start(uart_tx_actual_start),
    .tx_done(),  // 外部UART的done信号不需要（使用板载UART的done）
    .uart_tx(uart_tx_ext)
);

// 外部 UART RX 输出：将 uart_rx 直接连接给 uart_rx_ext（用于示波器测量）
// 直接连接确保无延迟，完全同步
// 注意：uart_rx_ext 仅用于示波器测量，CH3保持独立使用 la_data_in[3]

// 控制器模块
controller u_controller(
    .clk(clk),
    .resetn(resetn),
    .uart_rx_data(uart_rx_data),
    .uart_rx_valid(uart_rx_valid),
    .uart_tx_data(uart_tx_data),
    .uart_tx_start(uart_tx_start),
    .uart_tx_done(uart_tx_done),
    .sampler_enable(sampler_enable),
    .trigger_detected(trigger_detected),
    .trigger_mask(trigger_mask),
    .trigger_type(trigger_type),
    .trigger_pattern(trigger_pattern),
    .buffer_write_en(buffer_write_en),
    .buffer_read_en(buffer_read_en),
    .buffer_clear(buffer_clear),
    .buffer_full(buffer_full),
    .buffer_empty(buffer_empty),
    .buffer_sample_count(buffer_sample_count),
    .buffer_data_out(buffer_data_out),
    .freq_divider(freq_divider),
    .freq_update(freq_update),
    .duty_cycle_high(duty_cycle_high),
    .duty_update(duty_update),
    .sample_rate_divider(sample_rate_divider),
    .sample_rate_update(sample_rate_update),
    .state_out(controller_state)
);

// 频率生成器模块
freq_gen u_freq_gen(
    .clk(clk),
    .resetn(resetn),
    .freq_divider(freq_divider),
    .freq_update(freq_update),
    .duty_cycle_high(duty_cycle_high),
    .duty_update(duty_update),
    .freq_out(freq_out)
);

// 状态 LED 输出（参考LED_NANO9K配置方式）
// LED状态显示：
// 000 (IDLE):     全灭
// 001 (CONFIG):   LED0亮
// 010 (ARM):      LED1亮
// 011 (SAMPLING): LED0+LED1亮
// 100 (READY):    LED2亮
// 101 (TRANSMIT): LED0+LED2亮
// 110 (SET_FREQ): LED1+LED2亮
assign led_state = controller_state;

endmodule

