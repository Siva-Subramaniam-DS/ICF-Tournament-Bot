# Changelog

All notable changes to the ICF Tournament Bot project will be documented in this file.

## [3.0.0] - 2025-09-07

### Added
- ICF Tournament Bot branding throughout the application
- Logo integration for event posters (Logo_ICF_2025_400.png)
- Comprehensive documentation updates with current configuration
- Version tracking in all major files

### Changed
- **BREAKING**: Simplified role system from 5 roles to 2 roles:
  - `helpers_tournament` (ID: 1385296509289107671)
  - `organizers` (ID: 1385296705179619450)
- **BREAKING**: Updated channel configuration:
  - `schedules` (ID: 1413926551044751542)
  - `match_results` (ID: 1413924771699097721)
  - `match_reports` (ID: 1414247921896919182)
- Updated all documentation to reflect ICF Tournament Bot branding
- Modernized Python dependencies (pytz 2024.1)

### Removed
- **BREAKING**: Staff attendance functionality (transcript-like feature)
- Old channel references (`take_schedule`, `results`, `staff_attendance`)
- Old role references (`judge`, `head_helper`, `helper_team`)
- Deprecated "The Devil's Spot" branding

### Fixed
- Channel reference consistency across all files
- Role permission checks updated for new role system
- Judge ping functionality updated for new roles

### Technical
- All files updated with September 7, 2025 timestamps
- Version 3.0.0 applied across all documentation
- Production-ready configuration implemented

## [2.0.0] - Legacy

### Added
- Enhanced error handling and logging
- Persistent judge assignment storage
- Improved embed manipulation
- Configuration management system
- Comprehensive validation

## [1.0.0] - Legacy

### Added
- Basic event management
- Judge assignment system
- Discord slash commands
- Simple embed handling

---

**Note**: This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.