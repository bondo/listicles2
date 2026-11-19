package fixture

// LongParameterList: a plain function with many parameters is still reported (only @Composable is exempt).
fun combine(
    a: Int,
    b: Int,
    c: Int,
    d: Int,
    e: Int,
    f: Int,
    g: Int,
    h: Int,
): Int = a + b + c + d + e + f + g + h
