# 🗂️ EMPTY_FILE_GUIDELINES.md

This document defines the policy for using "empty file contracts" across the Arcade Assistant and ArcadiaOS projects.

## 🎯 Purpose

These files act as *scaffold markers* that define the purpose and boundaries of a directory before any code is written.

## 📁 Example Contracts

- `components/+input` → Only input elements (buttons, sliders, toggles)
- `services/+usb-monitoring` → Manages USB/HID events
- `diagnostics/+config-validation` → Validates emulation configs

## ✅ Agent Behavior

- Do not write outside the contract description.
- Do not rename or delete contract stubs.
- Always prefer `+`-prefixed folders to prevent name collisions.

## 🛠 How to Add One

1. Create the folder or file with `+` prefix
2. Add a `README.md` or `TODO.md` explaining intent
3. Commit it before AI agents start editing the tree