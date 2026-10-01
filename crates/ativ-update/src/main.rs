fn main() {
    if let Err(error) = tlo_updater::client::run(
        "com.tlolabs.ativ",
        "tlolabs/ativ",
        env!("CARGO_PKG_VERSION"),
    ) {
        eprintln!("Update failed: {error}");
        std::process::exit(1);
    }
}
