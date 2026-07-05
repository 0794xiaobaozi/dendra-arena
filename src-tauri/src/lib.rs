use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, LogicalSize, Manager, State};

struct BackendProcess {
    child: Child,
    stdin: ChildStdin,
}

struct BackendState(Mutex<Option<BackendProcess>>);

fn spawn_backend(app: AppHandle) -> Result<BackendProcess, String> {
    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().ok_or("invalid project root")?.to_path_buf();
    let configured = std::env::var("ARENA_BACKEND").ok();
    let bundled = app.path().resource_dir().ok().map(|dir| dir.join("arena-backend.exe")).filter(|p| p.exists());
    let mut command = if let Some(path) = configured.or_else(|| bundled.map(|b| b.to_string_lossy().into_owned())) {
        let mut c = Command::new(path);
        let resource_dir = app.path().resource_dir().unwrap_or(project_root.clone());
        c.env("PYTHONPATH", resource_dir.join("backend")).current_dir(&resource_dir);
        c
    } else {
        let pixi_python = project_root.join(".pixi").join("envs").join("default").join("python.exe");
        let mut command = Command::new(if pixi_python.exists() { pixi_python.into_os_string() } else { "python".into() });
        command.args(["-m", "arena_backend.main"]);
        command.env("PYTHONPATH", project_root.join("backend"));
        command.current_dir(&project_root);
        command
    };
    command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|error| format!("failed to start backend: {error}"))?;
    let stdin = child.stdin.take().ok_or("backend stdin unavailable")?;
    let stdout = child.stdout.take().ok_or("backend stdout unavailable")?;
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            match serde_json::from_str::<Value>(&line) {
                Ok(message) => { let _ = app.emit("backend-message", message); }
                Err(error) => { let _ = app.emit("backend-message", json!({"kind":"transport_error","error":error.to_string()})); }
            }
        }
        let _ = app.emit("backend-message", json!({"kind":"event","type":"backend_stopped","payload":{}}));
    });
    Ok(BackendProcess { child, stdin })
}

#[tauri::command]
fn start_backend(app: AppHandle, state: State<'_, BackendState>) -> Result<(), String> {
    let mut backend = state.0.lock().map_err(|_| "backend lock poisoned")?;
    if backend.as_mut().is_some_and(|process| process.child.try_wait().ok().flatten().is_none()) {
        return Ok(());
    }
    *backend = Some(spawn_backend(app)?);
    Ok(())
}

#[tauri::command]
fn backend_command(app: AppHandle, state: State<'_, BackendState>, message: Value) -> Result<(), String> {
    let mut backend = state.0.lock().map_err(|_| "backend lock poisoned")?;
    if backend.is_none() {
        *backend = Some(spawn_backend(app)?);
    }
    let process = backend.as_mut().ok_or("backend unavailable")?;
    serde_json::to_writer(&mut process.stdin, &message).map_err(|error| error.to_string())?;
    process.stdin.write_all(b"\n").map_err(|error| error.to_string())?;
    process.stdin.flush().map_err(|error| error.to_string())
}

#[tauri::command]
async fn select_save_directory() -> Result<Option<String>, String> {
    Ok(rfd::AsyncFileDialog::new()
        .set_title("Select arena save directory")
        .pick_folder()
        .await
        .map(|handle| handle.path().to_string_lossy().into_owned()))
}

#[tauri::command]
async fn select_protocol_yaml() -> Result<Option<String>, String> {
    Ok(rfd::AsyncFileDialog::new()
        .set_title("Import arena protocol YAML")
        .add_filter("YAML protocol", &["yml", "yaml"])
        .pick_file()
        .await
        .map(|handle| handle.path().to_string_lossy().into_owned()))
}

#[tauri::command]
async fn select_session_file() -> Result<Option<String>, String> {
    Ok(rfd::AsyncFileDialog::new()
        .set_title("Load arena session")
        .add_filter("Arena Session", &["arena.json"])
        .pick_file()
        .await
        .map(|handle| handle.path().to_string_lossy().into_owned()))
}

pub fn run() {
    tauri::Builder::default()
        .manage(BackendState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![start_backend, backend_command, select_save_directory, select_protocol_yaml, select_session_file])
        .setup(|app| {
            let state = app.state::<BackendState>();
            let process = spawn_backend(app.handle().clone()).map_err(std::io::Error::other)?;
            *state.0.lock().map_err(|_| std::io::Error::other("backend lock poisoned"))? = Some(process);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_max_size(Some(LogicalSize::new(1440.0, 1000.0)));
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            use tauri::WindowEvent;
            match event {
                WindowEvent::Destroyed => {
                    let state = window.state::<BackendState>();
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut backend) = guard.take() {
                            let _ = backend.child.kill();
                            let _ = backend.child.wait();
                        }
                    };
                }
                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running arena");
}
