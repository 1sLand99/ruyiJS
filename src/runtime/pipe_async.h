#ifndef RUYIJS_PIPE_ASYNC_H
#define RUYIJS_PIPE_ASYNC_H
#include "runtime/pipe.h"
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <cstdint>
#include <deque>

namespace ruyijs {
struct PipeOperation {
  OVERLAPPED value{};
  bool pending = false;
};
// The buffers passed to Windows remain in this object or at the front of its
// deque until their own completion is harvested, including cancellation.
struct PipeAsync {
  PipeOperation accept, read, write;
  bool server = false, connected = false, received = false;
  PipeResult terminal = PipeResult::Pending;
  uint32_t readLength = 0, writeLength = 0;
  size_t readOffset = 0, writeOffset = 0, queuedBytes = 0;
  bool readingBody = false;
  std::string incoming;
  std::deque<std::string> outgoing;
  PipeAsync();
  ~PipeAsync();
  bool Valid() const;
};
PipeAsync* NewPipeAsync();
void CancelPipeOperation(HANDLE pipe, PipeOperation& operation);
PipeResult PipeError(DWORD error);
PipeResult PipeAccept(HANDLE pipe, PipeAsync& state);
PipeResult PipeIo(HANDLE pipe, PipeOperation& operation, bool writing,
                   void* bytes, DWORD size, DWORD* transferred);
PipeResult PipeRead(HANDLE pipe, PipeAsync& state);
PipeResult PipeWrite(HANDLE pipe, PipeAsync& state);
}
#endif
