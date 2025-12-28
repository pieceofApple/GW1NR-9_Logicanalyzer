`timescale 1ns / 1ps
// 可调频率生成器模块
// 功能: 生成可调频率和占空比的方波输出
// 初始频率: 10kHz, 初始占空比: 50%
module freq_gen(
    input clk,              // 系统时钟 27MHz
    input resetn,
    input [31:0] freq_divider,  // 频率分频比 (27MHz / 目标频率 / 2)
    input freq_update,      // 频率更新使能
    input [31:0] duty_cycle_high,  // 高电平持续时间（时钟周期数）
    input duty_update,      // 占空比更新使能
    output reg freq_out     // 频率输出
);

// 初始频率: 10kHz
// 分频比 = 27MHz / 10kHz / 2 = 1350
localparam INIT_DIVIDER = 32'd1350;
// 初始占空比: 50% (高电平持续时间 = 分频比)
localparam INIT_DUTY_HIGH = 32'd1350;

reg [31:0] period_reg;     // 完整周期寄存器（时钟周期数）
reg [31:0] duty_high_reg;   // 高电平持续时间寄存器（时钟周期数）
reg [31:0] counter;        // 分频计数器
reg output_state;          // 输出状态：1=高电平，0=低电平

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        period_reg <= INIT_DIVIDER * 2;  // 完整周期 = 分频比 * 2
        duty_high_reg <= INIT_DUTY_HIGH;  // 初始占空比50%
        counter <= 32'd0;
        freq_out <= 1'b0;
        output_state <= 1'b0;
    end else begin
        // 更新分频比和占空比
        if (freq_update) begin
            period_reg <= freq_divider * 2;  // 完整周期 = 分频比 * 2
            // 更新频率时，保持当前占空比，但需要重新计算高电平时间
            // 如果当前占空比超过50%，限制为50%
            if (duty_high_reg > freq_divider) begin
                duty_high_reg <= freq_divider;  // 限制为50%占空比
            end
            counter <= 32'd0;
            freq_out <= 1'b0;
            output_state <= 1'b0;
        end else if (duty_update) begin
            // 更新占空比时，确保高电平时间在有效范围内
            // 高电平时间范围: [1, period_reg - 1]
            if (duty_cycle_high == 32'd0) begin
                duty_high_reg <= 32'd1;  // 最小为1个时钟周期
            end else if (duty_cycle_high >= period_reg) begin
                duty_high_reg <= period_reg - 1;  // 最大为周期-1（接近100%占空比）
            end else begin
                duty_high_reg <= duty_cycle_high;
            end
            counter <= 32'd0;
            freq_out <= 1'b0;
            output_state <= 1'b0;
        end else begin
            // 分频计数
            if (output_state == 1'b0) begin
                // 低电平阶段：等待 (period_reg - duty_high_reg) 个周期
                if (counter >= period_reg - duty_high_reg - 1) begin
                    counter <= 32'd0;
                    output_state <= 1'b1;
                    freq_out <= 1'b1;  // 切换到高电平
                end else begin
                    counter <= counter + 1'b1;
                end
            end else begin
                // 高电平阶段：等待 duty_high_reg 个周期
                if (counter >= duty_high_reg - 1) begin
                    counter <= 32'd0;
                    output_state <= 1'b0;
                    freq_out <= 1'b0;  // 切换到低电平
                end else begin
                    counter <= counter + 1'b1;
                end
            end
        end
    end
end

endmodule

