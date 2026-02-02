import { hotkeyBridge } from './ws/hotkey.js';

export function setupGracefulShutdown(server, wss) {
  let shutdownInProgress = false;

  const gracefulShutdown = async (signal) => {
    if (shutdownInProgress) {
      console.log('Shutdown already in progress...');
      return;
    }

    shutdownInProgress = true;
    console.log(`\n🛑 Received ${signal}. Starting graceful shutdown...`);

    // Set a timeout for forceful shutdown
    const forceShutdownTimeout = setTimeout(() => {
      console.log('❌ Forceful shutdown due to timeout');
      process.exit(1);
    }, 10000); // 10 seconds

    try {
      // Shutdown hotkey bridge
      hotkeyBridge.shutdown();

      // Close WebSocket server
      if (wss) {
        console.log('Closing WebSocket connections...');
        wss.clients.forEach((ws) => {
          ws.terminate();
        });
        wss.close();
      }

      // Close HTTP/HTTPS server
      if (server) {
        console.log('Closing HTTP server...');
        await new Promise((resolve) => {
          server.close(resolve);
        });
      }

      // Cancel any pending timers or intervals
      // Note: In a real application, you'd clean up any background tasks here

      clearTimeout(forceShutdownTimeout);
      console.log('✅ Gateway shut down gracefully');
      process.exit(0);

    } catch (err) {
      console.error('❌ Error during shutdown:', err);
      clearTimeout(forceShutdownTimeout);
      process.exit(1);
    }
  };

  // Handle shutdown signals
  process.on('SIGINT', () => gracefulShutdown('SIGINT'));
  process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

  // Handle uncaught exceptions
  process.on('uncaughtException', (err) => {
    console.error('❌ Uncaught Exception:', err);
    gracefulShutdown('UNCAUGHT_EXCEPTION');
  });

  process.on('unhandledRejection', (err) => {
    console.error('❌ Unhandled Rejection:', err);
    gracefulShutdown('UNHANDLED_REJECTION');
  });
}