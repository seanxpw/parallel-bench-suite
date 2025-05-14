#ifndef PERF_CONTROL_H
#define PERF_CONTROL_H

#include <iostream>
#include <string>

#include <unistd.h> // For write, read, close
#include <string.h> // For strcmp, strlen, memset
#include <stdlib.h> // For atoi (not used in this version of init)
#include <fcntl.h>  // For open() and O_WRONLY, O_RDONLY
#include <cstdio>   // For perror
#include <errno.h>  // For errno
// Global file descriptors, initialized to -1 (invalid)
// Definition of global variables, initialized to an invalid state
int g_perf_ctl_fd = -1;
int g_perf_ctl_ack_fd = -1;

namespace PerfControl {

    // Define default fixed paths for the FIFOs
    // 你可以根据需要修改这些路径
    const char* const DEFAULT_CTL_PIPE_PATH = "/tmp/my_app_perf_ctl.fifo";
    const char* const DEFAULT_ACK_PIPE_PATH = "/tmp/my_app_perf_ack.fifo";

    /**
     * @brief Initializes perf control by opening named FIFOs at predefined paths.
     *
     * Call this early in your main() function.
     *
     * @param ctl_pipe_path Path to the control FIFO (perf reads commands from here).
     * @param ack_pipe_path Path to the acknowledgment FIFO (perf writes acks here).
     * @return true if FIFOs were successfully opened, false otherwise.
     */
    bool init(const char* ctl_pipe_path = DEFAULT_CTL_PIPE_PATH,
              const char* ack_pipe_path = DEFAULT_ACK_PIPE_PATH);

    /**
     * @brief Sends the "enable" command to perf to start profiling.
     */
    bool start_profiling(const char* section_name = "default_section");

    /**
     * @brief Sends the "disable" command to perf to stop profiling.
     */
    bool stop_profiling(const char* section_name = "default_section");

    /**
     * @brief Closes the file descriptors opened by init().
     *
     * Call this before your program exits if init() was successful.
     */
    void cleanup();

} // namespace PerfControl

namespace PerfControl {

// (DEFAULT_CTL_PIPE_PATH and DEFAULT_ACK_PIPE_PATH are defined in the header or here)

bool init(const char* ctl_pipe_path, const char* ack_pipe_path) {
    if (g_perf_ctl_fd != -1 || g_perf_ctl_ack_fd != -1) {
        std::cout << "[PerfControl] Warning: Already initialized. Call cleanup() first if re-initializing." << std::endl;
        return (g_perf_ctl_fd != -1 && g_perf_ctl_ack_fd != -1);
    }

    std::cout << "[PerfControl] Initializing by opening FIFOs: CTL='" << ctl_pipe_path
              << "', ACK='" << ack_pipe_path << "'" << std::endl;

    // Open control pipe for writing.
    // This call might block until 'perf' (the reader) opens its end of the pipe.
    // This is usually fine because 'perf' should be started by the script and be ready.
    g_perf_ctl_fd = open(ctl_pipe_path, O_WRONLY);
    if (g_perf_ctl_fd == -1) {
        std::string err_msg = "[PerfControl] ERROR: Failed to open control FIFO for writing: " + std::string(ctl_pipe_path);
        perror(err_msg.c_str());
        return false;
    }

    // Open acknowledgment pipe for reading.
    // This might also block until 'perf' (the writer) opens its end.
    g_perf_ctl_ack_fd = open(ack_pipe_path, O_RDONLY);
    if (g_perf_ctl_ack_fd == -1) {
        std::string err_msg = "[PerfControl] ERROR: Failed to open acknowledgment FIFO for reading: " + std::string(ack_pipe_path);
        perror(err_msg.c_str());
        // Clean up the already opened control FD if ack FD fails
        if (g_perf_ctl_fd != -1) {
            close(g_perf_ctl_fd);
            g_perf_ctl_fd = -1;
        }
        return false;
    }

    std::cout << "[PerfControl] Successfully opened FIFOs: ctl_fd=" << g_perf_ctl_fd
              << ", ack_fd=" << g_perf_ctl_ack_fd << std::endl;
    return true;
}

// Helper function (largely unchanged from previous version, but now directly uses globals)
bool send_command_and_wait_ack(const char* command, const char* section_name) {
    if (g_perf_ctl_fd < 0 || g_perf_ctl_ack_fd < 0) { // Check for -1 from failed open
        // std::cout << "[PerfControl] Skipped sending '" << command << "' for section '" << section_name
        //           << "': Perf FDs not valid (ctl: " << g_perf_ctl_fd << ", ack: " << g_perf_ctl_ack_fd << ")." << std::endl;
        return true; // Not a failure if FDs aren't open; program just runs without perf control.
    }

    ssize_t cmd_len = strlen(command) + 1; // +1 for null terminator
    ssize_t bytes_written = write(g_perf_ctl_fd, command, cmd_len);

    if (bytes_written == -1) {
        std::string err_msg = "[PerfControl] ERROR writing '" + std::string(command) + "' to perf_ctl_fd for section '" + section_name + "'";
        perror(err_msg.c_str());
        return false;
    }
     if (bytes_written < cmd_len) {
        std::cerr << "[PerfControl] ERROR: Incomplete write for command '" << command << "' for section '" << section_name
                  << "'. Wrote " << bytes_written << ", expected " << cmd_len << std::endl;
        return false;
    }


    char ack_buffer[32];
    memset(ack_buffer, 0, sizeof(ack_buffer));
    ssize_t bytes_read = read(g_perf_ctl_ack_fd, ack_buffer, sizeof(ack_buffer) - 1);

    if (bytes_read <= 0) {
        std::string err_intro = "[PerfControl] ERROR reading ack from perf_ctl_ack_fd after sending '" + std::string(command) + "' for section '" + section_name + "'";
        if (bytes_read == 0) {
            std::cerr << err_intro << ". Perf might have closed the pipe or exited prematurely." << std::endl;
        } else {
            perror(err_intro.c_str());
        }
        return false;
    }

    if (strncmp(ack_buffer, "ack", 3) != 0) {
        std::cerr << "[PerfControl] ERROR: Did not receive proper 'ack' from perf after sending '" << command
                  << "' for section '" << section_name << "'. Received: '" << ack_buffer << "'" << std::endl;
        return false;
    }
    return true;
}

bool start_profiling(const char* section_name) {
    return send_command_and_wait_ack("enable", section_name);
}

bool stop_profiling(const char* section_name) {
    return send_command_and_wait_ack("disable", section_name);
}

void cleanup() {
    bool closed_any = false;
    if (g_perf_ctl_fd != -1) {
        // std::cout << "[PerfControl] Closing ctl_fd=" << g_perf_ctl_fd << std::endl;
        if (close(g_perf_ctl_fd) == -1) {
            perror("[PerfControl] ERROR closing ctl_fd");
        }
        g_perf_ctl_fd = -1; // Mark as closed/invalid
        closed_any = true;
    }
    if (g_perf_ctl_ack_fd != -1) {
        // std::cout << "[PerfControl] Closing ack_fd=" << g_perf_ctl_ack_fd << std::endl;
        if (close(g_perf_ctl_ack_fd) == -1) {
            perror("[PerfControl] ERROR closing ack_fd");
        }
        g_perf_ctl_ack_fd = -1; // Mark as closed/invalid
        closed_any = true;
    }
    if (closed_any) {
        std::cout << "[PerfControl] Cleanup: Closed perf FDs." << std::endl;
    }
}

} // namespace PerfControl
#endif // PERF_CONTROL_H