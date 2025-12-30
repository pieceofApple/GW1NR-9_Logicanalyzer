`timescale 1ns / 1ps
// 启动发送模块
// 功能: 复位后自动通过UART发送"start"字符串
module startup_tx(
    input clk,
    input resetn,
    output [7:0] tx_data,      // 要发送的数据
    output tx_start,           // 发送启动信号
    input tx_done,             // 发送完成信号
    output startup_done        // 启动发送完成标志
);

// "start" 字符串 (5个字符)
localparam STARTUP_MSG_LEN = 4'd5;
reg [7:0] startup_msg [0:4];

// 初始化消息
initial begin
    startup_msg[0] = 8'h73;  // 's'
    startup_msg[1] = 8'h74;  // 't'
    startup_msg[2] = 8'h61;  // 'a'
    startup_msg[3] = 8'h72;  // 'r'
    startup_msg[4] = 8'h74;  // 't'
end

// 状态定义
localparam IDLE = 3'b000;
localparam DELAY = 3'b001;
localparam SEND = 3'b010;
localparam WAIT = 3'b011;
localparam DONE = 3'b100;

// 延迟计数器（等待UART稳定，约1ms @27MHz）
localparam DELAY_CNT = 27'd27000;  // 27MHz / 1000 = 27000

reg [2:0] state;
reg [2:0] char_index;  // 字符索引 (0-4)
reg [16:0] delay_counter;

assign tx_data = startup_msg[char_index];
assign tx_start = (state == SEND);
assign startup_done = (state == DONE);

always @(posedge clk or negedge resetn) begin
    if (~resetn) begin
        state <= IDLE;
        char_index <= 3'd0;
        delay_counter <= 17'd0;
    end else begin
        case (state)
            IDLE: begin
                // 复位释放后，进入延迟状态
                state <= DELAY;
                delay_counter <= 17'd0;
            end
            
            DELAY: begin
                // 延迟一段时间，等待UART稳定
                if (delay_counter >= DELAY_CNT) begin
                    state <= SEND;
                    char_index <= 3'd0;
                end else begin
                    delay_counter <= delay_counter + 1'b1;
                end
            end
            
            SEND: begin
                // 启动发送当前字符
                state <= WAIT;
            end
            
            WAIT: begin
                // 等待发送完成
                if (tx_done) begin
                    if (char_index == STARTUP_MSG_LEN - 1) begin
                        // 所有字符发送完成
                        state <= DONE;
                    end else begin
                        // 发送下一个字符
                        char_index <= char_index + 1'b1;
                        state <= SEND;
                    end
                end
            end
            
            DONE: begin
                // 启动发送完成，保持此状态
                state <= DONE;
            end
            
            default: begin
                state <= IDLE;
            end
        endcase
    end
end

endmodule

