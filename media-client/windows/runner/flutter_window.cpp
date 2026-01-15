#include "flutter_window.h"

#include <optional>
#include <windowsx.h>
#ifdef _DEBUG
#include <cstdio>
#endif

#include "flutter/generated_plugin_registrant.h"
#include "desktop_multi_window/desktop_multi_window_plugin.h"

static HWND g_main_window_handle = nullptr;
static DWORD g_process_id = 0;
static bool g_reenabling_main_window = false;
static UINT_PTR g_dump_timer_id = 0;
static constexpr UINT kDumpMessage = WM_APP + 1;

#ifdef _DEBUG
static void DumpProcessWindows(const char* tag) {
  if (g_process_id == 0) {
    g_process_id = GetCurrentProcessId();
  }

  std::printf("[multi_window] dump=%s main=%p enabled=%d\n", tag,
              g_main_window_handle,
              g_main_window_handle == nullptr ? -1
                                              : IsWindowEnabled(g_main_window_handle));

  EnumWindows(
      [](HWND hwnd, LPARAM) -> BOOL {
        DWORD pid = 0;
        GetWindowThreadProcessId(hwnd, &pid);
        if (pid != g_process_id) return TRUE;

        RECT r{};
        GetWindowRect(hwnd, &r);
        LONG_PTR style = GetWindowLongPtr(hwnd, GWL_STYLE);
        LONG_PTR ex_style = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
        HWND parent = GetParent(hwnd);
        HWND owner = GetWindow(hwnd, GW_OWNER);
        BOOL visible = IsWindowVisible(hwnd);
        BOOL enabled = IsWindowEnabled(hwnd);
        char class_name[256]{};
        GetClassNameA(hwnd, class_name, sizeof(class_name));

        std::printf(
            "[multi_window] hwnd=%p class=%s vis=%d en=%d style=0x%llx "
            "ex=0x%llx parent=%p owner=%p rect=[%ld,%ld,%ld,%ld]\n",
            hwnd, class_name, visible, enabled, (long long)style,
            (long long)ex_style, parent, owner, r.left, r.top, r.right, r.bottom);
        return TRUE;
      },
      0);

  if (g_main_window_handle == nullptr) return;

  std::printf("[multi_window] dump=%s main_children\n", tag);
  EnumChildWindows(
      g_main_window_handle,
      [](HWND hwnd, LPARAM) -> BOOL {
        RECT r{};
        GetWindowRect(hwnd, &r);
        LONG_PTR style = GetWindowLongPtr(hwnd, GWL_STYLE);
        LONG_PTR ex_style = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
        BOOL visible = IsWindowVisible(hwnd);
        BOOL enabled = IsWindowEnabled(hwnd);
        char class_name[256]{};
        GetClassNameA(hwnd, class_name, sizeof(class_name));
        std::printf(
            "[multi_window] child=%p class=%s vis=%d en=%d style=0x%llx ex=0x%llx "
            "rect=[%ld,%ld,%ld,%ld]\n",
            hwnd, class_name, visible, enabled, (long long)style,
            (long long)ex_style, r.left, r.top, r.right, r.bottom);
        return TRUE;
      },
      0);
}
#else
static void DumpProcessWindows(const char*) {}
#endif

static void MoveWindowAwayFromMain(HWND window_hwnd) {
  if (g_main_window_handle == nullptr || window_hwnd == nullptr) return;

  RECT main_rect{};
  if (!GetWindowRect(g_main_window_handle, &main_rect)) return;

  HMONITOR monitor = MonitorFromWindow(g_main_window_handle, MONITOR_DEFAULTTONEAREST);
  MONITORINFO mi{};
  mi.cbSize = sizeof(mi);
  if (!GetMonitorInfo(monitor, &mi)) return;

  RECT work = mi.rcWork;

  RECT win_rect{};
  if (!GetWindowRect(window_hwnd, &win_rect)) return;
  const int width = win_rect.right - win_rect.left;
  const int height = win_rect.bottom - win_rect.top;

  int target_x = main_rect.right + 12;
  int target_y = main_rect.top;

  if (target_x + width > work.right) {
    target_x = work.right - width;
  }
  if (target_x < work.left) {
    target_x = work.left;
  }
  if (target_y + height > work.bottom) {
    target_y = work.bottom - height;
  }
  if (target_y < work.top) {
    target_y = work.top;
  }

  SetWindowPos(window_hwnd, HWND_NOTOPMOST, target_x, target_y, 0, 0,
               SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
}

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  g_main_window_handle = GetHandle();
  DumpProcessWindows("main-created");

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  DesktopMultiWindowSetWindowCreatedCallback([](void *controller) {
    auto *flutter_view_controller =
        reinterpret_cast<flutter::FlutterViewController *>(controller);
    auto *registry = flutter_view_controller->engine();
    RegisterPlugins(registry);

    if (flutter_view_controller->view() != nullptr) {
      HWND sub_hwnd = flutter_view_controller->view()->GetNativeWindow();
      HWND window_hwnd = GetAncestor(sub_hwnd, GA_ROOT);
      if (window_hwnd != nullptr) {
        SetWindowLongPtr(window_hwnd, GWLP_HWNDPARENT, 0);
        SetWindowPos(window_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
        MoveWindowAwayFromMain(window_hwnd);
        LONG_PTR ex_style = GetWindowLongPtr(window_hwnd, GWL_EXSTYLE);
        ex_style |= WS_EX_NOACTIVATE;
        SetWindowLongPtr(window_hwnd, GWL_EXSTYLE, ex_style);
      }
    }

    if (g_main_window_handle != nullptr &&
        IsWindowEnabled(g_main_window_handle) == FALSE) {
      EnableWindow(g_main_window_handle, TRUE);
    }

    DumpProcessWindows("subwindow-created");
    if (g_main_window_handle != nullptr) {
      PostMessage(g_main_window_handle, kDumpMessage, 0, 0);
    }
  });
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  if (hwnd == g_main_window_handle && message == WM_NCHITTEST) {
    LRESULT hit = DefWindowProc(hwnd, message, wparam, lparam);
    if (flutter_controller_ != nullptr) {
      std::optional<LRESULT> engine_hit =
          flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                        lparam);
      if (engine_hit) {
        hit = *engine_hit;
      }
    }
    POINT pt = {GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
    if (flutter_controller_ != nullptr && flutter_controller_->view() != nullptr) {
      HWND flutter_view_hwnd = flutter_controller_->view()->GetNativeWindow();
      if (flutter_view_hwnd != nullptr) {
        RECT flutter_rect{};
        if (GetWindowRect(flutter_view_hwnd, &flutter_rect)) {
          if (PtInRect(&flutter_rect, pt) != 0) {
            hit = HTCLIENT;
            HWND capture = GetCapture();
            if (capture != nullptr && capture != hwnd && capture != flutter_view_hwnd) {
#ifdef _DEBUG
              char cap_class[256]{};
              GetClassNameA(capture, cap_class, sizeof(cap_class));
              std::printf("[multi_window] release capture=%p class=%s\n", capture,
                          cap_class);
#endif
              ReleaseCapture();
            }
          }
        }
      }
    } else {
      POINT pt_client = pt;
      if (ScreenToClient(hwnd, &pt_client)) {
        RECT client_rect{};
        if (GetClientRect(hwnd, &client_rect)) {
          if (PtInRect(&client_rect, pt_client) != 0) {
            hit = HTCLIENT;
          }
        }
      }
    }
#ifdef _DEBUG
    std::printf("[multi_window] main WM_NCHITTEST hit=%lld\n", (long long)hit);
#endif
    return hit;
  }

  switch (message) {
    case kDumpMessage:
      DumpProcessWindows("post-subwindow-created");
      if (g_dump_timer_id == 0) {
        g_dump_timer_id = SetTimer(hwnd, 1, 1500, nullptr);
      }
      return 0;
    case WM_TIMER:
      DumpProcessWindows("timer");
      if (g_dump_timer_id != 0) {
        KillTimer(hwnd, g_dump_timer_id);
        g_dump_timer_id = 0;
      }
      return 0;
    case WM_ENABLE:
      if (hwnd == g_main_window_handle && wparam == FALSE &&
          g_reenabling_main_window == false) {
        g_reenabling_main_window = true;
        EnableWindow(hwnd, TRUE);
        g_reenabling_main_window = false;
        return 0;
      }
      break;
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN:
    case WM_MBUTTONDOWN:
      if (hwnd == g_main_window_handle && flutter_controller_ != nullptr &&
          flutter_controller_->view() != nullptr) {
        ReleaseCapture();
        HWND flutter_view_hwnd = flutter_controller_->view()->GetNativeWindow();
        if (flutter_view_hwnd != nullptr) {
          SetForegroundWindow(hwnd);
          SetActiveWindow(hwnd);
          SetFocus(flutter_view_hwnd);
        }
      }
#ifdef _DEBUG
      if (hwnd == g_main_window_handle && message == WM_LBUTTONDOWN) {
        std::printf("[multi_window] main WM_LBUTTONDOWN\n");
      }
#endif
      break;
    case WM_MOUSEACTIVATE:
      if (hwnd == g_main_window_handle) {
        return MA_ACTIVATE;
      }
      break;
    default:
      break;
  }

  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
