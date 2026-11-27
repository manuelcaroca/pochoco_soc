// Top de la estrategia del Proyecto 4.
// Expone SPI para el maestro externo y carga el programa trade.hex en RAM.
module trade_top_compact (
  input  wire        i_Clk,
  output wire [3:0]  o_LED,
  input  wire [3:0]  i_Switch,

  output wire        o_Segment1_A, o_Segment1_B, o_Segment1_C, o_Segment1_D,
  output wire        o_Segment1_E, o_Segment1_F, o_Segment1_G,
  output wire        o_Segment2_A, o_Segment2_B, o_Segment2_C, o_Segment2_D,
  output wire        o_Segment2_E, o_Segment2_F, o_Segment2_G,

  input  wire        i_SPI_SCLK,
  input  wire        i_SPI_MOSI,
  input  wire        i_SPI_CS_n,
  output wire        o_SPI_MISO
);

  pochoco_soc #(.MemFile("sw/trade_hybrid_compact.hex"), .NumWords(128), .P4_HYBRID_SHIFT(1)) u_soc (
    .i_Clk(i_Clk), .o_LED(o_LED), .i_Switch(i_Switch),
    .o_Segment1_A(o_Segment1_A), .o_Segment1_B(o_Segment1_B),
    .o_Segment1_C(o_Segment1_C), .o_Segment1_D(o_Segment1_D),
    .o_Segment1_E(o_Segment1_E), .o_Segment1_F(o_Segment1_F),
    .o_Segment1_G(o_Segment1_G),
    .o_Segment2_A(o_Segment2_A), .o_Segment2_B(o_Segment2_B),
    .o_Segment2_C(o_Segment2_C), .o_Segment2_D(o_Segment2_D),
    .o_Segment2_E(o_Segment2_E), .o_Segment2_F(o_Segment2_F),
    .o_Segment2_G(o_Segment2_G),
    .i_SPI_SCLK(i_SPI_SCLK), .i_SPI_MOSI(i_SPI_MOSI),
    .i_SPI_CS_n(i_SPI_CS_n), .o_SPI_MISO(o_SPI_MISO)
  );

endmodule
