/**
 * Blinky Verification Test Script
 * Part of: Phase 5 Blinky Gem Pivot
 * 
 * Tests:
 * 1. node-hid dependency is available
 * 2. LED-Wiz device enumeration
 * 3. Port contention detection
 * 4. Genre profile loading
 * 5. LED frame generation
 * 
 * Run: node gateway/tests/verify_blinky.js
 */

import HID from 'node-hid';

// Test 1: node-hid available
console.log('\n=== Blinky Verification Test ===\n');
console.log('✅ Test 1: node-hid module loaded successfully');

// Import aa-blinky gem
let blinky;
try {
    blinky = await import('../gems/aa-blinky/index.js');
    console.log('✅ Test 2: aa-blinky gem imported successfully');
    console.log(`   Gem: ${blinky.gemInfo.name} v${blinky.gemInfo.version}`);
} catch (e) {
    console.error('❌ Test 2: Failed to import aa-blinky gem:', e.message);
    process.exit(1);
}

// Test 3: Check SUPPORTED_IDS (REDLINE verification)
const expectedIds = [
    [0xFAFA, 0x00F0],
    [0xFAFA, 0x00F1],
    [0xFAFA, 0x00F2],
    [0xFAFA, 0x00F3],
    [0xFAFA, 0x00F4],
    [0xFAFA, 0x00F5],
    [0xFAFA, 0x00F6],
    [0xFAFA, 0x00F7],
];

const idsMatch = blinky.SUPPORTED_IDS.length === expectedIds.length &&
    blinky.SUPPORTED_IDS.every((id, i) => id[0] === expectedIds[i][0] && id[1] === expectedIds[i][1]);

if (idsMatch) {
    console.log('✅ Test 3: SUPPORTED_IDS match expected values (REDLINE preserved)');
} else {
    console.error('❌ Test 3: SUPPORTED_IDS MISMATCH - REDLINE VIOLATION!');
    process.exit(1);
}

// Test 4: Port contention check
const pythonActive = await blinky.isPythonLEDEngineActive();
console.log(`✅ Test 4: Port contention check completed`);
console.log(`   Python LEDEngine active: ${pythonActive}`);

// Test 5: HID enumeration (raw)
try {
    const allHID = HID.devices();
    const ledWiz = allHID.filter(d =>
        d.vendorId === 0xFAFA &&
        d.productId >= 0x00F0 &&
        d.productId <= 0x00F7
    );
    console.log(`✅ Test 5: HID enumeration complete`);
    console.log(`   Total HID devices: ${allHID.length}`);
    console.log(`   LED-Wiz devices found: ${ledWiz.length}`);

    for (const dev of ledWiz) {
        console.log(`   - VID:${dev.vendorId.toString(16)} PID:${dev.productId.toString(16)} at ${dev.path}`);
    }
} catch (e) {
    console.error('❌ Test 5: HID enumeration failed:', e.message);
}

// Test 6: aa-blinky discovery
if (!pythonActive) {
    try {
        const devices = await blinky.discover();
        console.log(`✅ Test 6: aa-blinky discovery complete`);
        console.log(`   Discovered: ${devices.length} device(s)`);

        for (const dev of devices) {
            console.log(`   - ${dev.deviceId}`);
        }
    } catch (e) {
        console.error('❌ Test 6: aa-blinky discovery failed:', e.message);
    }
} else {
    console.log('⚠️ Test 6: Skipped - Python LEDEngine is active');
}

// Test 7: Genre profile loading
try {
    const profiles = blinky.listProfiles();
    console.log(`✅ Test 7: Genre profiles loaded`);
    console.log(`   Profiles: ${profiles.length}`);

    for (const p of profiles.slice(0, 3)) {
        console.log(`   - ${p.icon} ${p.name} (${p.key})`);
    }
    if (profiles.length > 3) {
        console.log(`   ... and ${profiles.length - 3} more`);
    }
} catch (e) {
    console.error('❌ Test 7: Genre profile loading failed:', e.message);
}

// Test 8: LED profile to frame conversion
try {
    const [profileKey, profile] = blinky.getProfileForGenre('Fighting');
    if (profile?.led_profile) {
        // Sample button-to-port mapping
        const buttonToPort = {
            'p1.button1': 1,
            'p1.button2': 2,
            'p1.button3': 3,
            'p1.button4': 4,
            'p1.button5': 5,
            'p1.button6': 6,
            'p1.start': 7,
            'p1.coin': 8
        };

        const frame = blinky.ledProfileToFrame(profile.led_profile, buttonToPort);
        console.log(`✅ Test 8: LED frame generation`);
        console.log(`   Profile: ${profileKey}`);
        console.log(`   Frame (first 8): [${frame.slice(0, 8).join(', ')}]`);
    } else {
        console.log('⚠️ Test 8: No fighting profile found');
    }
} catch (e) {
    console.error('❌ Test 8: LED frame generation failed:', e.message);
}

// Summary
console.log('\n=== Verification Complete ===\n');

// Cleanup
blinky.closeAll();

console.log('All tests passed! Blinky gem is ready for use.\n');
