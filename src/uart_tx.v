`timescale 1ns / 1ps
// UART 发送模块
// 功能: 将数据通过 UART 发送到 PC
// 波特率: 115200 (可配置)
module uart_tx(
    input clk,              // 系统时钟 27MHz
    input resetn,
    input [7:0] data_in,   // 要发送的数据
    input tx_start,        // 发送启动信号
    output reg tx_done,    // 发送完成信号
    output reg uart_tx     // UART 发送线
);

// 波特率计算: 27MHz / 115200 ≈ 234.375
// 使用 234 分频，实际波特率 ≈ 115384.6 (误差 < 0.1%)
localparam BAUD_DIV = 9'd234;
localparam BAUD_DIV_HALF = 9'd117;

// 状态定义
localparam IDLE = 2'b00;
localparam START = 2'b01;
localparam DATA = 2'b10;
localparam STOP = 2'b11;

reg [1:0] state;
reg [8:0] baud_counter;    // 波特率计数器
reg [2:0] bit_index;        // 数据位索引 (0-7)
reg [7:0] tx_data;          // 发送数据寄存器

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        state <= IDLE;
        baud_counter <= 9'd0;
        bit_index <= 3'd0;
        tx_data <= 8'd0;
        uart_tx <= 1'b1;    // 空闲状态为高电平
        tx_done <= 1'b0;
    end else begin
        case (state)
            IDLE: begin
                uart_tx <= 1'b1;
                tx_done <= 1'b0;
                if (tx_start) begin
                    state <= START;
                    tx_data <= data_in;
                    baud_counter <= 9'd0;
                end
            end
            
            START: begin
                uart_tx <= 1'b0;  // 起始位
                if (baud_counter == BAUD_DIV - 1) begin
                    baud_counter <= 9'd0;
                    state <= DATA;
                    bit_index <= 3'd0;
                end else begin
                    baud_counter <= baud_counter + 1'b1;
                end
            end
            
            DATA: begin
                uart_tx <= tx_data[bit_index];
                if (baud_counter == BAUD_DIV - 1) begin
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
                uart_tx <= 1'b1;  // 停止位
                if (baud_counter == BAUD_DIV - 1) begin
                    baud_counter <= 9'd0;
                    state <= IDLE;
                    tx_done <= 1'b1;
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

