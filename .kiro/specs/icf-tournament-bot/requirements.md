# Requirements Document

## Introduction

The ICF-Tournament-Bot is a Discord bot designed to manage and facilitate ICF (International Canoe Federation) tournament operations. The bot provides comprehensive tournament management features including match scheduling, judge assignment, rule management, result tracking, and automated notifications. It serves as a centralized system for tournament organizers, judges, and participants to coordinate tournament activities efficiently.

**Last Updated:** September 7, 2025  
**Version:** 3.0.0  
**Current Configuration:**
- Channels: schedules (1413926551044751542), match_results (1413924771699097721), match_reports (1414247921896919182)
- Roles: helpers_tournament (1385296509289107671), organizers (1385296705179619450)

## Requirements

### Requirement 1

**User Story:** As a tournament organizer, I want to schedule matches with specific teams and time slots, so that participants know when and where their matches will take place.

#### Acceptance Criteria

1. WHEN an organizer creates a match schedule THEN the system SHALL create a dedicated channel for the match
2. WHEN a match is scheduled THEN the system SHALL send notifications to team captains with match details
3. WHEN a match time is set THEN the system SHALL automatically schedule reminder notifications 10 minutes before the match
4. IF a match is scheduled THEN the system SHALL display match information in an organized embed format
5. WHEN match details are created THEN the system SHALL include team captain mentions, match time, and event channel information

### Requirement 2

**User Story:** As a judge, I want to take and release match assignments, so that I can manage my judging responsibilities effectively.

#### Acceptance Criteria

1. WHEN a judge clicks "Take Schedule" THEN the system SHALL assign them to the match if they have capacity
2. WHEN a judge is assigned THEN the system SHALL add them to the match channel with appropriate permissions
3. WHEN a judge releases a schedule THEN the system SHALL remove them from the match channel and make the schedule available again
4. IF a judge already has 3 assignments THEN the system SHALL prevent them from taking additional schedules
5. WHEN a judge assignment changes THEN the system SHALL update the match embed and notify participants
6. WHEN a judge takes a schedule THEN the system SHALL disable the "Take Schedule" button and enable the "Release Schedule" button

### Requirement 3

**User Story:** As a tournament organizer, I want to manage tournament rules centrally, so that all participants have access to consistent and up-to-date rules.

#### Acceptance Criteria

1. WHEN an organizer enters new rules THEN the system SHALL save them persistently to storage
2. WHEN rules are updated THEN the system SHALL track the user who made the changes and timestamp
3. WHEN participants request rules THEN the system SHALL display the current rules in a formatted embed
4. IF no rules exist THEN the system SHALL display an appropriate message indicating rules need to be set
5. WHEN rules are edited THEN the system SHALL provide a modal interface for easy text input
6. WHEN rules are displayed THEN the system SHALL show metadata including last updated by and timestamp

### Requirement 4

**User Story:** As a team captain, I want to receive automated reminders about my matches, so that I don't miss important tournament events.

#### Acceptance Criteria

1. WHEN a match is 10 minutes away THEN the system SHALL send reminder notifications to team captains and judges
2. WHEN reminders are sent THEN the system SHALL include match time, opponent information, and judge details
3. WHEN a reminder is scheduled THEN the system SHALL calculate the correct timing based on match datetime
4. IF a match time is updated THEN the system SHALL reschedule the reminder accordingly
5. WHEN reminders are sent THEN the system SHALL mention all relevant participants in the notification

### Requirement 5

**User Story:** As a tournament administrator, I want role-based access control, so that only authorized users can perform administrative functions.

#### Acceptance Criteria

1. WHEN a user attempts judge functions THEN the system SHALL verify they have Judge or Head Organizer role
2. WHEN a user attempts rule management THEN the system SHALL verify they have Head Organizer role
3. WHEN unauthorized access is attempted THEN the system SHALL display appropriate error messages
4. IF a user has proper permissions THEN the system SHALL allow access to corresponding functions
5. WHEN permission checks fail THEN the system SHALL log the attempt and deny access

### Requirement 6

**User Story:** As a tournament organizer, I want to track match results and maintain tournament records, so that I can manage tournament progression and statistics.

#### Acceptance Criteria

1. WHEN match results are submitted THEN the system SHALL store them in the designated results channel
2. WHEN results are recorded THEN the system SHALL include match details, participants, and outcome
3. WHEN tournament data is needed THEN the system SHALL provide access to historical match information
4. IF results need correction THEN the system SHALL allow authorized users to update them
5. WHEN results are finalized THEN the system SHALL notify relevant participants and organizers

### Requirement 7

**User Story:** As a system administrator, I want the bot to handle errors gracefully and maintain data persistence, so that tournament operations continue smoothly even during technical issues.

#### Acceptance Criteria

1. WHEN errors occur THEN the system SHALL log them appropriately and continue operation
2. WHEN the bot restarts THEN the system SHALL restore scheduled events and judge assignments from persistent storage
3. WHEN data is modified THEN the system SHALL save changes to persistent storage immediately
4. IF storage operations fail THEN the system SHALL retry and notify administrators of issues
5. WHEN concurrent operations occur THEN the system SHALL prevent race conditions and data corruption

### Requirement 8

**User Story:** As a tournament participant, I want clear visual feedback and status updates, so that I understand the current state of matches and assignments.

#### Acceptance Criteria

1. WHEN match status changes THEN the system SHALL update embed colors and content accordingly
2. WHEN buttons are interacted with THEN the system SHALL provide immediate visual feedback
3. WHEN assignments are made THEN the system SHALL clearly display who is assigned to what role
4. IF actions are not permitted THEN the system SHALL explain why through clear error messages
5. WHEN information is displayed THEN the system SHALL use consistent formatting and branding