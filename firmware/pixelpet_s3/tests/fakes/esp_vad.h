#pragma once
#include <stdint.h>
typedef struct FakeVad* vad_handle_t;
typedef enum { VAD_MODE_1=1 } vad_mode_t;
typedef enum { VAD_SILENCE=0, VAD_SPEECH=1 } vad_state_t;
#ifdef __cplusplus
extern "C" {
#endif
vad_handle_t vad_create(vad_mode_t mode);
vad_state_t vad_process(vad_handle_t handle,int16_t* data,int rate,int frame_ms);
void vad_destroy(vad_handle_t handle);
#ifdef __cplusplus
}
#endif
