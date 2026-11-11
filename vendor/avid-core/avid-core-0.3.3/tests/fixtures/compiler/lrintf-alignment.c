/* Reduced from the legal unaligned row accesses in FFmpeg's gblur.
 * Windows long is 32 bits; LLVM's SSE2 vector lrint load pattern must not
 * select aligned CVTPS2DQ memory operands for an arbitrary float pointer.
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

__attribute__((noinline))
static void convert(uint8_t *dst, const float *src, int width, int height)
{
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++)
            dst[x] = lrintf(src[x]);
        dst += width;
        src += width;
    }
}

int main(int argc, char **argv)
{
    const int width = argc > 1 ? atoi(argv[1]) : 90;
    if (width < 1 || width > 256) return 2;
    float *src = malloc((size_t)width * 4 * sizeof(*src));
    uint8_t *dst = malloc((size_t)width * 4);
    if (!src || !dst) return 3;
    for (int i = 0; i < width * 4; i++) src[i] = 3.25f;
    convert(dst, src, width, 4);
    for (int i = 0; i < width * 4; i++) if (dst[i] != 3) return 4;
    printf("width=%d correct\n", width);
    free(dst); free(src);
    return 0;
}
