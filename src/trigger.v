`timescale 1ns / 1ps
// 触发逻辑模块
// 功能: 检测触发条件
module trigger(
    input clk,
    input resetn,
    input [7:0] data,           // 输入数据
    input [7:0] data_prev,      // 上一周期的数据（用于边沿检测）
    input [7:0] trigger_mask,   // 触发通道掩码（1=启用该通道触发）
    input [1:0] trigger_type,    // 触发类型: 00=上升沿, 01=下降沿, 10=模式, 11=组合
    input [7:0] trigger_pattern, // 触发模式（用于模式触发）
    output reg trigger_detected  // 触发检测信号
);

// 边沿检测
wire [7:0] rising_edge  = data & ~data_prev;  // 上升沿
wire [7:0] falling_edge = ~data & data_prev;   // 下降沿

// 模式匹配
wire pattern_match = (data & trigger_mask) == (trigger_pattern & trigger_mask);

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        trigger_detected <= 1'b0;
    end else begin
        case (trigger_type)
            2'b00: begin  // 上升沿触发
                trigger_detected <= |(rising_edge & trigger_mask);
            end
            2'b01: begin  // 下降沿触发
                trigger_detected <= |(falling_edge & trigger_mask);
            end
            2'b10: begin  // 模式触发
                trigger_detected <= pattern_match;
            end
            2'b11: begin  // 组合触发（上升沿或下降沿）
                trigger_detected <= |((rising_edge | falling_edge) & trigger_mask);
            end
            default: begin
                trigger_detected <= 1'b0;
            end
        endcase
    end
end

endmodule

