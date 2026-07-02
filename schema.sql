-- Основные таблицы системы

CREATE TABLE IF NOT EXISTS schools (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'subject_teacher',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1
);
CREATE INDEX idx_teachers_telegram ON teachers(telegram_id);

CREATE TABLE IF NOT EXISTS classes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    grade INTEGER,
    letter VARCHAR(5),
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1,
    UNIQUE (name, school_id)
);

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE NOT NULL,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1,
    meal_type VARCHAR(10) NOT NULL DEFAULT 'paid'
);
CREATE INDEX idx_students_class ON students(class_id);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE NOT NULL,
    session_date DATE NOT NULL DEFAULT CURRENT_DATE,
    start_time TIMESTAMP DEFAULT NOW() NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1,
    UNIQUE (class_id, session_date, school_id)
);
CREATE INDEX idx_sessions_date_status ON attendance_sessions(session_date, status);

CREATE TABLE IF NOT EXISTS attendance_records (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES attendance_sessions(id) ON DELETE CASCADE NOT NULL,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE NOT NULL,
    is_present BOOLEAN NOT NULL DEFAULT TRUE,
    reason VARCHAR(255)
);
CREATE INDEX idx_records_session ON attendance_records(session_id);
CREATE INDEX idx_records_student ON attendance_records(student_id);

CREATE TABLE IF NOT EXISTS registration_requests (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    class_name VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1
);
CREATE INDEX idx_regreq_telegram_school_status ON registration_requests(telegram_id, school_id, status);

-- Таблицы для питания

CREATE TABLE IF NOT EXISTS meal_requests (
    id SERIAL PRIMARY KEY,
    class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE NOT NULL,
    request_date DATE NOT NULL DEFAULT CURRENT_DATE,
    submitted_by_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE NOT NULL DEFAULT 1,
    submitted_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE (class_id, request_date, school_id)
);

CREATE TABLE IF NOT EXISTS meal_request_items (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES meal_requests(id) ON DELETE CASCADE NOT NULL,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE NOT NULL,
    is_eating BOOLEAN NOT NULL DEFAULT TRUE,
    meal_type VARCHAR(10) NOT NULL DEFAULT 'paid'
);