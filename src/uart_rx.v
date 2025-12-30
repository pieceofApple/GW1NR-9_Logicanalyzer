`timescale 1ns / 1ps
// UART 接收模块
// 功能: 从 PC 接收控制命令
// 波特率: 115200
module uart_rx(
    input clk,              // 系统时钟 27MHz
    input resetn,
    input uart_rx,         // UART 接收线
    output reg [7:0] data_out, // 接收到的数据
    output reg data_valid      // 数据有效信号
);

// 波特率分频
localparam BAUD_DIV = 9'd234;
localparam BAUD_DIV_HALF = 9'd117;

// 状态定义
localparam IDLE = 2'b00;
localparam START = 2'b01;
localparam DATA = 2'b10;
localparam STOP = 2'b11;

reg [1:0] state;
reg [8:0] baud_counter;
reg [2:0] bit_index;
reg [7:0] rx_data;
reg uart_rx_sync;          // 同步后的接收信号
reg uart_rx_prev;          // 上一周期的接收信号

// 输入同步（防止亚稳态）
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        uart_rx_sync <= 1'b1;
        uart_rx_prev <= 1'b1;
    end else begin
        uart_rx_prev <= uart_rx_sync;
        uart_rx_sync <= uart_rx;
    end
end

// 边沿检测
wire start_bit = ~uart_rx_sync & uart_rx_prev;

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        state <= IDLE;
        baud_counter <= 9'd0;
        bit_index <= 3'd0;
        rx_data <= 8'd0;
        data_out <= 8'd0;
        data_valid <= 1'b0;
    end else begin
        data_valid <= 1'b0;
        
        case (state)
            IDLE: begin
                if (start_bit) begin
                    state <= START;
                    baud_counter <= BAUD_DIV_HALF;  // 在起始位中间采样
                end
            end
            
            START: begin
                if (baud_counter == BAUD_DIV - 1) begin
                    baud_counter <= 9'd0;
                    state <= DATA;
                    bit_index <= 3'd0;
                end else begin
                    baud_counter <= baud_counter + 1'b1;
                end
            end
            
            DATA: begin
                if (baud_counter == BAUD_DIV - 1) begin
                    rx_data[bit_index] <= uart_rx_sync;
                    baud_counter <= 9'd0;
                    if (bit_index == 3'd7) begin
                        state <= STOP;
                    end else begin
                        bit_index <= bit_index + 1'b1;
                    end
                end else begin
                    baud_counter <= baud_counter + 1'b1;
                end
            end
            
            STOP: begin
                if (baud_counter == BAUD_DIV - 1) begin
                    data_out <= rx_data;
                    data_valid <= 1'b1;
                    state <= IDLE;
                    baud_counter <= 9'd0;
                end else begin
                    baud_counter <= baud_counter + 1'b1;
                end
            end
            
            default: begin
                state <= IDLE;
            end
        endcase
    end
end

endmodule

