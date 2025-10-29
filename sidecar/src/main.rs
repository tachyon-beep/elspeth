use anyhow::Result;
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "elspeth_sidecar=debug".into()),
        )
        .init();

    info!("Elspeth Sidecar Daemon starting...");

    // TODO: Load config, start server

    Ok(())
}
