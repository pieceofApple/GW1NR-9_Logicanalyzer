`timescale 1ns / 1ps
// 基础采样器模块
// 功能: 以固定频率采样输入信号
module sampler(
    input clk,              // 采样时钟 (27MHz)
    input resetn,           // 复位信号，低有效
    input [7:0] data_in,    // 8通道输入信号
    input enable,           // 采样使能
    output reg [7:0] data_out,  // 采样数据输出
    output reg valid            // 数据有效信号
);

// 简单的同步采样（在采样时钟上升沿采样）
// enable信号为高时，采样输入信号并输出有效标志
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        data_out <= 8'b0;
        valid <= 1'b0;
    end else begin
        if (enable) begin
            data_out <= data_in;  // 采样输入信号
            valid <= 1'b1;        // 数据有效
        end else begin
            // enable为低时，保持数据但清除valid标志
            // 这样确保只有enable为高时的数据才被认为是有效的
            valid <= 1'b0;
        end
    end
end

endmodule

