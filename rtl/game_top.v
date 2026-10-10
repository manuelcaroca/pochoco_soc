// Copyright 2026 Universidad de los Andes.
// game_top.v — Módulo Top-Level para Go Board FPGA

module game_top #(
    parameter MemFile = "sw/game.hex"
) (
    input  wire       i_Clk,
    input  wire [3:0] i_Switch,
    output wire [3:0] o_LED,

    // Segmentos Display 1
    output wire       o_Segment1_A, o_Segment1_B, o_Segment1_C,
    output wire       o_Segment1_D, o_Segment1_E, o_Segment1_F, o_Segment1_G,

    // Segmentos Display 2 
    output wire       o_Segment2_A, o_Segment2_B, o_Segment2_C,
    output wire       o_Segment2_D, o_Segment2_E, o_Segment2_F, o_Segment2_G
);

    // Instancia del SoC Pochoco respetando sus nombres de puertos originales
    pochoco_soc #(
        .MemFile(MemFile)
    ) u_soc (
        .i_Clk(i_Clk),
        .o_LED(o_LED),
        .i_Switch(i_Switch),

        .o_Segment1_A(o_Segment1_A), .o_Segment1_B(o_Segment1_B),
        .o_Segment1_C(o_Segment1_C), .o_Segment1_D(o_Segment1_D),
        .o_Segment1_E(o_Segment1_E), .o_Segment1_F(o_Segment1_F),
        .o_Segment1_G(o_Segment1_G),

        .o_Segment2_A(o_Segment2_A), .o_Segment2_B(o_Segment2_B),
        .o_Segment2_C(o_Segment2_C), .o_Segment2_D(o_Segment2_D),
        .o_Segment2_E(o_Segment2_E), .o_Segment2_F(o_Segment2_F),
        .o_Segment2_G(o_Segment2_G),

        // Entradas SPI no utilizadas en el top nivel
        .i_SPI_SCLK(1'b0),
        .i_SPI_MOSI(1'b0),
        .i_SPI_CS_n(1'b1),
        .o_SPI_MISO()
    );

endmodule