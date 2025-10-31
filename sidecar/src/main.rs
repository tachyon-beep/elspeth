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

    // Get config path from command-line argument or use default
    let config_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/etc/elspeth/sidecar.toml".to_string());

    info!("Loading config from: {}", config_path);

    // Load config (no default - mode must be explicit)
    let config = Config::load(&config_path)
        .context("Failed to load config - ensure mode is set to 'sidecar' or 'standalone'")?;

    // Start server
    let server = Server::new(config)?;
    server.run().await?;

    Ok(())
}
