module \$mul (A, B, Y);

    parameter A_SIGNED = 0;
    parameter B_SIGNED = 0;
    parameter A_WIDTH = 3;
    parameter B_WIDTH = 3;
    parameter Y_WIDTH = 6;

    input [A_WIDTH - 1:0] A;
    input [B_WIDTH - 1:0] B;
    output [Y_WIDTH - 1:0] Y;

    wire                    _TECHMAP_FAIL_ = Y_WIDTH <= 2 || A_WIDTH <= 2 || B_WIDTH <= 2;
    wire [256 * 8 - 1:0]    _TECHMAP_DO_ = "proc; opt";

    // Hard multiplier operand widths
    localparam  HARDMUL_WIDTH_A = {{ module.ports.a|length }};
    localparam  HARDMUL_WIDTH_B = {{ module.ports.b|length }};

    // Use only unsigned multipliers for now
    wire                                            sign_a;
    assign sign_a = A[A_WIDTH - 1];

    wire                                            sign_b;
    assign sign_b = B[B_WIDTH - 1];

    // Calculate lower_axb = A[0 +: A_WIDTH - 1] * B[0 +: B_WIDTH - 1]
    // chop up A
    localparam  N_SGMTS_A = ((A_WIDTH - 1) / HARDMUL_WIDTH_A) + ((A_WIDTH - 1) % HARDMUL_WIDTH_A > 0 ? 1 : 0);
    wire [HARDMUL_WIDTH_A - 1:0]                    sgmts_a     [0 : N_SGMTS_A - 1];

    genvar ai;
    generate for (ai = 0; ai < N_SGMTS_A; ai = ai + 1) begin: g_sgmt_a
        if ((ai + 1) * HARDMUL_WIDTH_A > A_WIDTH - 1) begin
            assign sgmts_a[ai] = { {HARDMUL_WIDTH_A {1'b0}}, A[A_WIDTH - 2 : ai * HARDMUL_WIDTH_A]};
        end else begin
            assign sgmts_a[ai] = A[ai * HARDMUL_WIDTH_A +: HARDMUL_WIDTH_A];
        end
    end endgenerate

    // chop up B
    localparam  N_SGMTS_B = ((B_WIDTH - 1) / HARDMUL_WIDTH_B) + ((B_WIDTH - 1) % HARDMUL_WIDTH_B > 0 ? 1 : 0);
    wire [HARDMUL_WIDTH_B - 1:0]                    sgmts_b     [0 : N_SGMTS_B - 1];

    genvar bi;
    generate for (bi = 0; bi < N_SGMTS_B; bi = bi + 1) begin: g_sgmt_b
        if ((bi + 1) * HARDMUL_WIDTH_B > B_WIDTH - 1) begin
            assign sgmts_b[bi] = { {HARDMUL_WIDTH_B {1'b0}}, B[B_WIDTH - 2 : bi * HARDMUL_WIDTH_B]};
        end else begin
            assign sgmts_b[bi] = B[bi * HARDMUL_WIDTH_B +: HARDMUL_WIDTH_B];
        end
    end endgenerate

    // do partials
    wire [HARDMUL_WIDTH_A + HARDMUL_WIDTH_B - 1:0]  partial_axb [0 : N_SGMTS_A - 1][0 : N_SGMTS_B - 1];

    genvar ap, bp;
    generate for (ap = 0; ap < N_SGMTS_A; ap = ap + 1) begin: g_partial_a
        for (bp = 0; bp < N_SGMTS_B; bp = bp + 1) begin: g_partial_b
            {{ module.vpr_model }} #(
                .SIGNED(1'b0)
            ) i_mul (
                .a(sgmts_a[ap])
                ,.b(sgmts_b[bp])
                ,.x(partial_axb[ap][bp])
                );
        end
    end endgenerate

    // sum up
    reg [Y_WIDTH - 1:0]                             lower_axb;

    integer al, bl;
    always @* begin
        lower_axb = {Y_WIDTH {1'b0} };

        for (al = 0; al < N_SGMTS_A; al = al + 1) begin
            for (bl = 0; bl < N_SGMTS_B; bl = bl + 1) begin
                lower_axb = lower_axb + (partial_axb[al][bl] << (al * HARDMUL_WIDTH_A + bl * HARDMUL_WIDTH_B));
            end
        end
    end

    // handle final step
    reg [Y_WIDTH-1:0]                               y_pre;
    assign Y = y_pre;

    always @* begin
        y_pre = {Y_WIDTH {1'b0} };

        y_pre = y_pre + lower_axb;

        if (A_SIGNED == B_SIGNED)
            y_pre = y_pre + ((sign_a & sign_b) << (A_WIDTH + B_WIDTH - 2));
        else
            y_pre = y_pre - ((sign_a & sign_b) << (A_WIDTH + B_WIDTH - 2));

        if (sign_a)
            if (A_SIGNED)
                y_pre = y_pre - (B[0 +: B_WIDTH - 1] << (A_WIDTH - 1));
            else
                y_pre = y_pre + (B[0 +: B_WIDTH - 1] << (A_WIDTH - 1));
        
        if (sign_b)
            if (B_SIGNED)
                y_pre = y_pre - (A[0 +: A_WIDTH - 1] << (B_WIDTH - 1));
            else
                y_pre = y_pre + (A[0 +: A_WIDTH - 1] << (B_WIDTH - 1));
    end

endmodule
