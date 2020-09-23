module \$alu (A, B, CI, BI, X, Y, CO);
    parameter A_SIGNED = 0;
    parameter B_SIGNED = 0;
    parameter A_WIDTH = 1;
    parameter B_WIDTH = 1;
    parameter Y_WIDTH = 1;
    parameter _TECHMAP_CONSTVAL_CI_ = 0;
    parameter _TECHMAP_CONSTMSK_CI_ = 0;
    
    input [A_WIDTH-1:0] A;
    input [B_WIDTH-1:0] B;
    output [Y_WIDTH-1:0] X, Y;

    input CI, BI;
    output [Y_WIDTH-1:0] CO;

    wire _TECHMAP_FAIL_ = Y_WIDTH <= 2;

    wire [Y_WIDTH-1:0] A_buf, B_buf;
    \$pos #(.A_SIGNED(A_SIGNED), .A_WIDTH(A_WIDTH), .Y_WIDTH(Y_WIDTH)) A_conv (.A(A), .Y(A_buf));
    \$pos #(.A_SIGNED(B_SIGNED), .A_WIDTH(B_WIDTH), .Y_WIDTH(Y_WIDTH)) B_conv (.A(B), .Y(B_buf));

    wire [Y_WIDTH-1:0] AA = A_buf;
    wire [Y_WIDTH-1:0] BB = BI ? ~B_buf : B_buf;

    wire [Y_WIDTH-1:0] CO_CHAIN;
    wire CO_LAST;

    {{ model }} #(.CIN_FABRIC(1'b1)) cc_first (.a(AA[0]), .b(BB[0]), .cin_fabric(CI), .s(Y[0]), .cout(CO_CHAIN[0]));

    genvar i;
    generate for (i = 1; i < Y_WIDTH; i = i + 1) begin: slice
        {{ model }} cc (.a(AA[i]), .b(BB[i]), .cin(CO_CHAIN[i - 1]), .s(Y[i]), .cout(CO_CHAIN[i]));
    end endgenerate

    {{ model }} cc_last (.a(0), .b(0), .cin(CO_CHAIN[Y_WIDTH-1]), .s(CO_LAST));

    assign X = AA ^ BB;
    assign CO = {CO_LAST, CO_CHAIN[0+:Y_WIDTH-1]};

endmodule
