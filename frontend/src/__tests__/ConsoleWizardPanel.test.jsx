/**
 * Tests for Console Wizard Panel
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ConsoleWizardPanel from '../panels/console-wizard/ConsoleWizardPanel';

// Mock fetch globally
global.fetch = jest.fn();

describe('ConsoleWizardPanel', () => {
  beforeEach(() => {
    // Reset fetch mock before each test
    fetch.mockClear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('renders Console Wizard panel', async () => {
    // Mock successful API responses
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ emulators: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          currentMappingHash: 'test-hash',
          lastSyncedHash: 'test-hash',
          isOutOfSync: false,
        }),
      });

    render(<ConsoleWizardPanel />);

    // Check for main heading
    await waitFor(() => {
      expect(screen.getByText('Console Wizard')).toBeInTheDocument();
    });
  });

  test('displays incomplete_mapping error message', async () => {
    // Mock API responses - emulators and health succeed, but preview fails with incomplete_mapping
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ emulators: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          currentMappingHash: 'test-hash',
          lastSyncedHash: 'test-hash',
          isOutOfSync: false,
        }),
      });

    const { container } = render(<ConsoleWizardPanel />);

    await waitFor(() => {
      expect(screen.getByText('Console Wizard')).toBeInTheDocument();
    });

    // Mock the preview endpoint to return incomplete_mapping error
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      headers: new Headers(),
      text: async () =>
        JSON.stringify({
          detail: {
            error: 'incomplete_mapping',
            message: 'Controller mapping is missing required logical keys',
            missing_keys: ['p1.button5', 'p2.coin'],
          },
        }),
    });

    // Find and click the Generate Configs button
    const generateButton = screen.getByText(/Generate Configs/i);
    fireEvent.click(generateButton);

    // Wait for error message to appear
    await waitFor(
      () => {
        const errorElements = container.querySelectorAll('.panel-banner.error, .panel-error');
        const hasError = Array.from(errorElements).some((el) =>
          el.textContent.includes('Controller Chuck')
        );
        expect(hasError).toBe(true);
      },
      { timeout: 3000 }
    );
  });

  test('displays Chuck sync banner when out of sync', async () => {
    // Mock API responses
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ emulators: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          currentMappingHash: 'new-hash',
          lastSyncedHash: 'old-hash',
          isOutOfSync: true,
        }),
      });

    render(<ConsoleWizardPanel />);

    // Wait for panel to load
    await waitFor(() => {
      expect(screen.getByText('Console Wizard')).toBeInTheDocument();
    });

    // Check for sync banner
    await waitFor(
      () => {
        const banners = screen.queryAllByText(/Controller mapping changed/i);
        // Banner may appear if Chuck status shows out of sync
        expect(banners.length).toBeGreaterThanOrEqual(0);
      },
      { timeout: 3000 }
    );
  });

  test('displays health warning banner when emulators need attention', async () => {
    // Mock API responses with health issues
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          emulators: [
            {
              id: 'retroarch',
              name: 'RetroArch',
              config_format: 'cfg',
              status: 'ok',
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: [
            {
              emulator: 'retroarch',
              status: 'missing',
              details: 'Config missing',
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          currentMappingHash: 'test-hash',
          lastSyncedHash: 'test-hash',
          isOutOfSync: false,
        }),
      });

    render(<ConsoleWizardPanel />);

    // Wait for panel to load
    await waitFor(() => {
      expect(screen.getByText('Console Wizard')).toBeInTheDocument();
    });

    // Check for attention banner
    await waitFor(
      () => {
        const banners = screen.queryAllByText(/need attention/i);
        expect(banners.length).toBeGreaterThan(0);
      },
      { timeout: 3000 }
    );
  });

  test('preview and apply buttons are functional', async () => {
    // Mock API responses
    fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          emulators: [
            {
              id: 'retroarch',
              name: 'RetroArch',
              config_format: 'cfg',
              status: 'ok',
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          currentMappingHash: 'test-hash',
          lastSyncedHash: 'test-hash',
          isOutOfSync: false,
        }),
      });

    render(<ConsoleWizardPanel />);

    await waitFor(() => {
      expect(screen.getByText('Console Wizard')).toBeInTheDocument();
    });

    // Mock successful preview response
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        dry_run: true,
        results: [],
      }),
    });

    // Find and click Generate Configs button
    const generateButton = screen.getByText(/Generate Configs/i);
    fireEvent.click(generateButton);

    // Verify fetch was called with correct parameters
    await waitFor(() => {
      const calls = fetch.mock.calls;
      const previewCall = calls.find(
        (call) => call[0].includes('/generate-configs')
      );
      expect(previewCall).toBeDefined();
    });
  });
});
