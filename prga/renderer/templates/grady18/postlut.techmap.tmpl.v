module \$lut (A, Y);
    parameter WIDTH = 0;
    parameter LUT = 0;

    (* force_downto *)
    input [WIDTH - 1:0] A;
    output Y;

    generate if (WIDTH == 6) begin
        wire [1:0] lut5out;

        \$lut #(.LUT(LUT[31: 0]), .WIDTH(5)) lut0 (.A(A[4:0]), .Y(lut5out[0])); 
        \$lut #(.LUT(LUT[63:32]), .WIDTH(5)) lut1 (.A(A[4:0]), .Y(lut5out[1])); 
        m_mux2 mux (.i(lut5out), .sel(A[5]), .o(Y));
    end else begin
        wire _TECHMAP_FAIL_ = 1;
    end endgenerate

endmodule
