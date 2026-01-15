#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>
#ifdef _DEBUG
#include <cstdio>
#endif

#include "flutter_window.h"
#include "utils.h"

#ifdef _DEBUG
static HHOOK g_call_wnd_proc_hook = nullptr;
static FILE* g_winmsg_log = nullptr;

static void PrintHwndInfo(const char* tag, HWND hwnd) {
  if (hwnd == nullptr) {
    std::printf("[winmsg] %s hwnd=null\n", tag);
    return;
  }
  char class_name[256]{};
  GetClassNameA(hwnd, class_name, sizeof(class_name));
  RECT r{};
  GetWindowRect(hwnd, &r);
  std::printf("[winmsg] %s hwnd=%p class=%s rect=[%ld,%ld,%ld,%ld]\n", tag, hwnd,
              class_name, r.left, r.top, r.right, r.bottom);
}

static LRESULT CALLBACK CallWndProcHook(int nCode, WPARAM wParam, LPARAM lParam) {
  if (nCode >= 0) {
    auto* cwp = reinterpret_cast<CWPSTRUCT*>(lParam);
    switch (cwp->message) {
      case WM_LBUTTONDOWN:
      case WM_LBUTTONUP:
      case WM_RBUTTONDOWN:
      case WM_RBUTTONUP:
      case WM_MOUSEMOVE:
      case WM_NCHITTEST: {
        char class_name[256]{};
        GetClassNameA(cwp->hwnd, class_name, sizeof(class_name));
        HWND capture = GetCapture();
        HWND fg = GetForegroundWindow();
        HWND focus = GetFocus();
        if (g_winmsg_log != nullptr) {
          std::fprintf(g_winmsg_log,
                       "[winmsg] msg=0x%04x hwnd=%p class=%s capture=%p fg=%p focus=%p\n",
                       (unsigned)cwp->message, cwp->hwnd, class_name, capture, fg, focus);
          std::fflush(g_winmsg_log);
        } else {
          std::printf(
              "[winmsg] msg=0x%04x hwnd=%p class=%s capture=%p fg=%p focus=%p\n",
              (unsigned)cwp->message, cwp->hwnd, class_name, capture, fg, focus);
        }
        break;
      }
      default:
        break;
    }
  }
  return CallNextHookEx(g_call_wnd_proc_hook, nCode, wParam, lParam);
}
#endif

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Point origin(10, 10);
  Win32Window::Size size(1280, 720);
  if (!window.Create(L"media_client", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

#ifdef _DEBUG
  fopen_s(&g_winmsg_log, "winmsg.log", "w");
  PrintHwndInfo("main", window.GetHandle());
  g_call_wnd_proc_hook = SetWindowsHookEx(WH_CALLWNDPROC, CallWndProcHook, nullptr,
                                         GetCurrentThreadId());
  if (g_call_wnd_proc_hook == nullptr) {
    std::printf("[winmsg] SetWindowsHookEx failed err=%lu\n", GetLastError());
  }
#endif

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

#ifdef _DEBUG
  if (g_call_wnd_proc_hook != nullptr) {
    UnhookWindowsHookEx(g_call_wnd_proc_hook);
    g_call_wnd_proc_hook = nullptr;
  }
  if (g_winmsg_log != nullptr) {
    std::fclose(g_winmsg_log);
    g_winmsg_log = nullptr;
  }
#endif

  ::CoUninitialize();
  return EXIT_SUCCESS;
}
