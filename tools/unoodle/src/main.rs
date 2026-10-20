use std::io::{Read, Write};

fn main() {
    let size: usize = std::env::args()
        .nth(1)
        .and_then(|value| value.parse().ok())
        .expect("usage: unoodle-block <decompressed size> < block");
    let mut input = Vec::new();
    std::io::stdin().read_to_end(&mut input).expect("read stdin");
    let mut output = vec![0u8; size];
    let written = oozextract::Extractor::new()
        .read_from_slice(&input, &mut output)
        .expect("decompress");
    std::io::stdout().write_all(&output[..written]).expect("write stdout");
}
