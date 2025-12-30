`timescale 1ns / 1ps
// 采样率分频器模块
// 功能: 将系统时钟分频，生成可配置的采样时钟
// 分频比 = 1: 27MHz (不分频，最大采样率)
// 分频比 = N: 27MHz / N
// 注意: 使用27MHz系统时钟
module sample_rate_divider(
    input clk,              // 系统时钟 (27MHz)
    input resetn,           // 复位信号，低有效
    input [31:0] divider,  // 分频比 (1 = 27MHz, 2 = 13.5MHz, ...)
    input update,           // 更新分频比信号
    output reg sample_clk_en  // 采样时钟使能信号（高电平有效一个周期）
);

// 默认分频比 (270 = 100kHz采样率 @ 27MHz)
// 27MHz / 270 = 100kHz
localparam DEFAULT_DIVIDER = 32'd270;

reg [31:0] current_divider;
reg [31:0] counter;

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        current_divider <= DEFAULT_DIVIDER;
        counter <= 32'd0;
        sample_clk_en <= 1'b0;
    end else begin
        sample_clk_en <= 1'b0;  // 默认低电平
        
        if (update) begin
            // 确保分频比至少为1
            if (divider == 32'd0) begin
                current_divider <= 32'd1;
            end else begin
                current_divider <= divider;
            end
            counter <= 32'd0;
            // update时立即产生一个sample_clk_en脉冲，确保采样可以立即开始
            // 这样即使分频比很大，也能立即开始采样
            sample_clk_en <= 1'b1;
        end else begin
            // 分频逻辑：
            // - divider = 1: 每个时钟周期产生脉冲（counter: 0->0，每个周期都满足条件）
            // - divider = 2: 每2个时钟周期产生脉冲（counter: 0->1->0，当counter=1时产生脉冲）
            // - divider = N: 每N个时钟周期产生脉冲（counter: 0->1->...->(N-1)->0，当counter=(N-1)时产生脉冲）
            if (current_divider == 32'd1) begin
                // 分频比为1时，每个时钟周期都产生脉冲
                sample_clk_en <= 1'b1;
                counter <= 32'd0;  // 保持为0
            end else if (counter >= current_divider - 1) begin
                // 分频比 > 1 时，当计数器达到 (divider-1) 时产生脉冲
                counter <= 32'd0;
                sample_clk_en <= 1'b1;  // 产生采样使能脉冲（持续一个时钟周期）
            end else begin
                counter <= counter + 1'b1;
            end
        end
    end
end

endmodule

