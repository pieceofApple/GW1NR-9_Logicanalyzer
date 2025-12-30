`timescale 1ns / 1ps
// BRAM 缓冲管理模块
// 功能: 管理采样数据的存储和读取
// 注意: 此模块需要综合工具推断为BRAM，如果失败请使用BRAM IP核
module bram_buffer(
    input clk,
    input resetn,
    input [7:0] data_in,        // 写入数据
    input write_en,             // 写使能
    input read_en,              // 读使能
    input clear,                // 清除缓冲区（开始新采样时使用）
    output [7:0] data_out,      // 读出数据
    output reg [15:0] write_addr, // 写地址 (16位，最大65535)
    output reg [15:0] read_addr,  // 读地址
    output reg full,            // 缓冲区满标志
    output reg empty,           // 缓冲区空标志
    output reg [15:0] sample_count // 已采样数量
);

// 缓冲区大小: 使用 48K 字节充分利用BRAM资源
// GW1NR-9 有 468K 位 BRAM (58.5KB)
// 设置为 48KB (384K bits) 充分利用资源，留84K bits余量给其他用途
// 使用 (* ram_style = "block" *) 属性确保综合为BRAM
localparam BUFFER_SIZE = 16'd49152;  // 48K 字节 = 384K 位 (使用82.1%的BRAM资源)

// BRAM 存储器声明
// 使用 (* ram_style = "block" *) 属性提示综合工具使用BRAM
(* ram_style = "block" *)
reg [7:0] mem [0:BUFFER_SIZE-1];

// 写操作
// 优化：确保BRAM推断成功，使用简单的写操作
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        write_addr <= 16'd0;
        sample_count <= 16'd0;
        full <= 1'b0;
    end else begin
        if (clear) begin
            // 清除缓冲区状态（只在非写入时清除，避免冲突）
            if (~write_en) begin
                write_addr <= 16'd0;
                sample_count <= 16'd0;
                full <= 1'b0;
            end
        end else if (write_en && ~full) begin
            // BRAM写操作：直接使用地址索引，确保推断为BRAM
            mem[write_addr] <= data_in;
            // 地址递增
            if (write_addr == BUFFER_SIZE - 1) begin
                write_addr <= 16'd0;
                full <= 1'b1;
            end else begin
                write_addr <= write_addr + 1'b1;
            end
            // 采样计数
            sample_count <= sample_count + 1'b1;
        end
    end
end

// 读操作
always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        read_addr <= 16'd0;
        empty <= 1'b1;
    end else begin
        if (clear) begin
            // 清除读地址和空标志（只在非读取时清除，避免冲突）
            if (~read_en) begin
                read_addr <= 16'd0;
                empty <= 1'b1;
            end
        end else begin
            if (read_en && ~empty) begin
                read_addr <= read_addr + 1'b1;
                
                // 检查是否已空
                if (read_addr == write_addr - 1) begin
                    empty <= 1'b1;
                end
            end else if (sample_count > 0) begin
                empty <= 1'b0;
            end
        end
    end
end

// 读数据输出
// 使用同步读取，确保BRAM推断成功
// BRAM读取：在时钟上升沿读取，数据在下一个周期有效
reg [7:0] data_out_reg;
always @(posedge clk) begin
    if (read_en && ~empty) begin
        data_out_reg <= mem[read_addr];  // 同步读取BRAM
    end
end
assign data_out = data_out_reg;

endmodule

