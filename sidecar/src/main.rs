use anyhow::{Context, Result};
use elspeth_sidecar::{config::Config, server::Server};
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

    // Load config (no default - mode must be explicit)
    let config = Config::load("/etc/elspeth/sidecar.toml")
        .context("Failed to load config - ensure mode is set to 'sidecar' or 'standalone'")?;

    // Start server
    let server = Server::new(config)?;
    server.run().await?;

    Ok(())
}
