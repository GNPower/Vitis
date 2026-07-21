/*
 * Minimal standalone application for the Vitis-On-Git ZedBoard example.
 *
 * It prints one line over the domain's configured UART and returns. The example
 * exists to exercise CREATE and BUILD end to end, not to do anything on
 * hardware.
 */
#include <stdio.h>

int main(void)
{
    printf("Hello from Vitis-On-Git (ZedBoard example)\n");
    return 0;
}
