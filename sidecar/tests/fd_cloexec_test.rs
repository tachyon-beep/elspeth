//! Test to verify Unix socket has FD_CLOEXEC flag set.
//!
//! This prevents file descriptors from being inherited by child processes,
//! which could allow plugins to access the sidecar socket.

use nix::fcntl::{fcntl, FcntlArg, FdFlag};
use std::os::unix::io::AsRawFd;
use tempfile::tempdir;
use tokio::net::UnixListener;

#[tokio::test]
async fn test_unix_socket_has_fd_cloexec() {
    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test_cloexec.sock");

    // Bind Unix socket (same as server.rs does)
    let listener = UnixListener::bind(&socket_path).expect("Failed to bind socket");

    // Get raw file descriptor
    let fd = listener.as_raw_fd();

    // Query FD flags
    let flags = fcntl(fd, FcntlArg::F_GETFD).expect("Failed to get FD flags");
    let fd_flags = FdFlag::from_bits(flags).expect("Invalid FD flags");

    // Verify FD_CLOEXEC is set
    assert!(
        fd_flags.contains(FdFlag::FD_CLOEXEC),
        "Unix socket should have FD_CLOEXEC flag set to prevent inheritance by child processes"
    );

    println!("✓ FD_CLOEXEC is set on Unix socket (flags: {:?})", fd_flags);
}

#[tokio::test]
async fn test_accepted_connection_has_fd_cloexec() {
    use std::os::unix::net::UnixStream as StdUnixStream;

    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test_accept_cloexec.sock");

    // Bind listener
    let listener = UnixListener::bind(&socket_path).expect("Failed to bind socket");

    // Connect in background
    let socket_path_clone = socket_path.clone();
    let client_handle = tokio::spawn(async move {
        tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
        StdUnixStream::connect(socket_path_clone).expect("Failed to connect");
    });

    // Accept connection
    let (stream, _) = listener
        .accept()
        .await
        .expect("Failed to accept connection");

    // Verify accepted stream has FD_CLOEXEC
    let fd = stream.as_raw_fd();
    let flags = fcntl(fd, FcntlArg::F_GETFD).expect("Failed to get FD flags");
    let fd_flags = FdFlag::from_bits(flags).expect("Invalid FD flags");

    assert!(
        fd_flags.contains(FdFlag::FD_CLOEXEC),
        "Accepted connection should have FD_CLOEXEC flag set"
    );

    println!(
        "✓ FD_CLOEXEC is set on accepted connection (flags: {:?})",
        fd_flags
    );

    client_handle.await.unwrap();
}
