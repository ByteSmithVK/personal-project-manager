-- database.sql
-- ---------------------------------------------------------------
-- Run this script in MySQL to create the database and table used
-- by the Personal Project Manager application.
--
--   mysql -u root -p < database.sql
--
-- ---------------------------------------------------------------

CREATE DATABASE IF NOT EXISTS personal_project_manager;
USE personal_project_manager;

CREATE TABLE IF NOT EXISTS guides (
    guide_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assigned_by_persons (
    person_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    description TEXT,
    technology VARCHAR(200),
    start_date DATE,
    end_date DATE,
    status ENUM('Not Started', 'In Progress', 'Completed', 'On Hold') DEFAULT 'Not Started',
    priority ENUM('Low', 'Medium', 'High') DEFAULT 'Medium',
    project_link VARCHAR(500),
    notes TEXT,
    assigned_by_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (assigned_by_id)
        REFERENCES assigned_by_persons(person_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_guides (
    project_id INT NOT NULL,
    guide_id INT NOT NULL,
    PRIMARY KEY (project_id, guide_id),
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE,
    FOREIGN KEY (guide_id)
        REFERENCES guides(guide_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Project Status Meetings
-- One project has many status/meeting updates.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_status_meetings (
    meeting_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    meeting_date DATE NOT NULL,
    meeting_title VARCHAR(200) NOT NULL,
    summary TEXT,
    current_status ENUM(
        'Not Started',
        'In Progress',
        'On Hold',
        'Completed',
        'Delayed'
    ) DEFAULT 'In Progress',
    decisions TEXT,
    action_items TEXT,
    next_meeting_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Project Milestones
-- One project has many milestones / deliverables.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_milestones (
    milestone_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    due_date DATE,
    status ENUM('Pending', 'In Progress', 'Completed', 'Delayed') DEFAULT 'Pending',
    completion_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Milestone Tasks (Sub-tasks for each milestone)
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS milestone_tasks (
    task_id INT AUTO_INCREMENT PRIMARY KEY,
    milestone_id INT NOT NULL,
    task_title VARCHAR(255) NOT NULL,
    is_completed TINYINT(1) DEFAULT 0,
    due_date DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (milestone_id)
        REFERENCES project_milestones(milestone_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Change Requests
-- One project has many change requests.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS change_requests (
    change_request_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    request_date DATE NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    reason TEXT,
    priority ENUM(
        'Low',
        'Medium',
        'High',
        'Critical'
    ) DEFAULT 'Medium',
    status ENUM(
        'Open',
        'In Progress',
        'Completed',
        'Rejected'
    ) DEFAULT 'Open',
    requested_by VARCHAR(150),
    completion_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Optional sample data. Safe to delete this block if you want to
-- start with an empty table.
-- ---------------------------------------------------------------

INSERT INTO projects
    (project_name, description, technology, start_date, end_date, status, priority, project_link, notes)
VALUES
    (
        'CSKD Foolproof System',
        'A fail-safe control and monitoring system for a small production line.',
        'Python, PLC Ladder Logic, MySQL',
        '2025-01-10',
        '2025-03-15',
        'Completed',
        'High',
        'https://github.com/example/cskd-foolproof-system',
        'Delivered on time. Consider adding a mobile alert feature in v2.'
    ),
    (
        'PLC Dashboard',
        'Web dashboard for visualizing real-time PLC sensor data.',
        'Flask, MySQL, Chart.js',
        '2025-04-01',
        NULL,
        'In Progress',
        'Medium',
        'https://github.com/example/plc-dashboard',
        'Need to finish the alarm-history page next.'
    ),
    (
        'DLD Elevator Control System',
        'Digital logic design project simulating an elevator controller using sequential circuits.',
        'VHDL, Digital Logic Design',
        '2024-09-01',
        '2024-12-01',
        'On Hold',
        'Low',
        NULL,
        'Paused to focus on the PLC Dashboard project. Revisit next semester.'
    );

-- Sample status meetings and change requests for the first sample
-- project ("CSKD Foolproof System"). Safe to delete if not needed.

INSERT INTO project_status_meetings
    (project_id, meeting_date, meeting_title, summary, current_status, decisions, action_items, next_meeting_date, notes)
VALUES
    (
        1,
        '2026-09-01',
        'Project Review',
        'Dashboard and report modules completed. Barcode module is under development.',
        'In Progress',
        'Proceed with barcode module using the existing scanner library.',
        'Complete barcode scanning backend.',
        '2026-09-08',
        NULL
    ),
    (
        1,
        '2026-09-08',
        'Project Review',
        'Barcode scanning backend is 60% complete. Testing planned for next week.',
        'In Progress',
        'Push testing start date to align with QA availability.',
        'Finish backend, prepare test cases.',
        '2026-09-15',
        NULL
    ),
    (
        1,
        '2026-09-15',
        'Weekly Project Review',
        'Dashboard and report modules completed. Barcode module is under development.',
        'In Progress',
        'Approved the carton-wise printing change requested by production.',
        'Complete barcode scanning backend.',
        '2026-09-22',
        NULL
    );

INSERT INTO change_requests
    (project_id, request_date, title, description, reason, priority, status, requested_by, completion_date, notes)
VALUES
    (
        1,
        '2026-08-10',
        'Add Report Filter',
        'Add a date-range filter to the production report screen.',
        'Requested by production team for faster reporting.',
        'Medium',
        'Completed',
        'Production Team',
        '2026-08-20',
        NULL
    ),
    (
        1,
        '2026-08-25',
        'Update Dashboard',
        'Refresh dashboard layout to show shift-wise output.',
        'Improve visibility for supervisors.',
        'Medium',
        'Completed',
        'Shift Supervisor',
        '2026-09-02',
        NULL
    ),
    (
        1,
        '2026-09-18',
        'Modify Barcode Printing Logic',
        'Barcode should be printed carton-wise instead of printing all cartons at once.',
        'Updated production requirement.',
        'High',
        'In Progress',
        'Production Manager',
        NULL,
        NULL
    );
