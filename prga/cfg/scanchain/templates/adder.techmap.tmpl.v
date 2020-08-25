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

    genvar i, j;
    generate for (i = 0; i < Y_WIDTH; i = i + 32) begin: slice
        adder #(.CIN_FABRIC(1'b1)) cc0 (.a(AA[i]), .b(BB[i]), .cin_fabric(i == 0 ? CI : CO[i - 1]), .s(Y[i]), .cout(CO_CHAIN[i]), .cout_fabric(CO[i]));

        for (j = i + 1; j < Y_WIDTH && j < i + 32; j = j + 1) begin: slice_inter
            adder cc (.a(AA[j]), .b(BB[j]), .cin(CO_CHAIN[j - 1]), .s(Y[j]), .cout(CO_CHAIN[j]), .cout_fabric(CO[j]));
        end
    end endgenerate

    assign X = AA ^ BB;

endmodule
