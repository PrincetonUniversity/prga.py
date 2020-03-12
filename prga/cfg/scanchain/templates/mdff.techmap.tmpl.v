(* techmap_celltype = "$dff $_DFF_P_" *)
module _dff (input D, C, output Q);
    parameter _TECHMAP_CELLTYPE_ = "";
    mdff dff (.clk(C), .D(D), .Q(Q));
endmodule

(* techmap_celltype = "$dffe $_DFFE_PP_" *)
module _dffe (input D, C, E, output Q);
    parameter _TECHMAP_CELLTYPE_ = "";
    mdff #(.ENABLE_CE(1'b1)) dff (.clk(C), .D(D), .Q(Q), .ce(E));
endmodule

module \$_DFFE_PN_ (input D, C, E, output Q);
    mdff #(.ENABLE_CE(1'b1)) dff (.clk(C), .D(D), .Q(Q), .ce(~E));
endmodule

module \$_DFF_PP0_ (input D, C, R, output Q);
    mdff #(.ENABLE_SR(1'b1)) dff (.clk(C), .D(D), .Q(Q), .sr(R));
endmodule

module \$_DFF_PN0_ (input D, C, R, output Q);
    mdff #(.ENABLE_SR(1'b1)) dff (.clk(C), .D(D), .Q(Q), .sr(~R));
endmodule

module \$_DFF_PP1_ (input D, C, R, output Q);
    mdff #(.ENABLE_SR(1'b1), .SR_SET(1'b1)) dff (.clk(C), .D(D), .Q(Q), .sr(R));
endmodule

module \$_DFF_PN1_ (input D, C, R, output Q);
    mdff #(.ENABLE_SR(1'b1), .SR_SET(1'b1)) dff (.clk(C), .D(D), .Q(Q), .sr(~R));
endmodule

