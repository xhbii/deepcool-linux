# AK620 G2 fan controls: implementation status

The Windows 1.2.14 application's AK620 G2 interface exposes these operations:

- Motherboard PWM synchronization.
- Silent AI / performance AI and sleep / office / gaming / overclocking presets.
- Manual PWM, acceleration and deceleration settings.
- RPM feedback.
- Display power and temperature alert settings.

The frontend's IPC parameters are not the device's HID packet layout. The main
implementation is stored as V8 serialized bytecode. Protocol investigation is
in progress; commands are enabled only after the report ID, field layout,
transport method and response interpretation are established.

The current released implementation sends telemetry reports only and leaves
fan configuration unchanged. Firmware updates and zero-RPM control are outside
the implemented scope.

The Linux policy layer has tests for manual duty, configurable monotonic
temperature curves, three Linux presets, immediate increases and gradual
decreases. Software control uses full duty at 80°C or when the temperature
sensor is unavailable. These presets are newly designed curves, not the
vendor's AI algorithm. This layer is not connected to the device until the
control packets are verified.

HID transport supports bounded nonblocking input reads and feature reports
whose lengths match the connected model's descriptor (IDs 2, 3 and 4: 64 bytes;
ID 5: 2 bytes, each including its ID). Transport support alone does not
establish the semantics of those reports.

Investigation files derived from the vendor application are kept locally and
are excluded from version control and release archives. Verified protocol
summaries and independently written implementations can be included here.
