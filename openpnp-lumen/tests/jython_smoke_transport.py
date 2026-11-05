# Jython transport to the Marlin/bus simulator pty (used by the Jython tests).
from java.io import FileInputStream, FileOutputStream
from java.lang import Thread, Runnable
from java.util.concurrent import LinkedBlockingQueue, TimeUnit


class PtyTransport(object):
    def __init__(self, port):
        self.out = FileOutputStream(port)
        self.inp = FileInputStream(port)
        self.q = LinkedBlockingQueue()
        transport = self

        class Reader(Runnable):
            def run(self):
                buf = []
                while True:
                    c = transport.inp.read()
                    if c < 0:
                        return
                    if c == 10:
                        transport.q.put("".join(buf).strip())
                        buf = []
                    else:
                        buf.append(chr(c))
        t = Thread(Reader())
        t.setDaemon(True)
        t.start()

    def transact_hex(self, hexs):
        self.out.write(bytearray("M485 " + hexs + "\n"))
        self.out.flush()
        reply = None
        while True:
            line = self.q.poll(3, TimeUnit.SECONDS)
            if line is None:
                return None
            if line.startswith("rs485-reply:"):
                reply = line.split(":", 1)[1].strip()
            elif line.startswith("ok"):
                return reply
