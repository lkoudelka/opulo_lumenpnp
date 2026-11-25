# -*- coding: utf-8 -*-
"""Zoom and pan for the Lumen windows' pictures (Jython, Swing), like OpenPnP's camera view.

Mouse wheel = zoom in / out at the mouse pointer, left drag = move the zoomed picture, right click = fit
again.  ZoomPan adds this to any JPanel that paints itself (the panel applies zp.apply(g) and maps clicks
with zp.to_view); ImageView is a ready panel for one image with an overlay painted in image pixels and
clicks reported in image pixels; image_window() opens it in a window with a text and buttons.
"""
from __future__ import absolute_import, division, print_function

from java.awt import BasicStroke, BorderLayout, Color, Dimension, FlowLayout, Font, Graphics2D, RenderingHints
from java.awt.event import MouseAdapter
from java.awt.geom import AffineTransform, Point2D
from java.awt.image import BufferedImage
from javax.swing import JButton, JEditorPane, JFrame, JPanel, JScrollPane, SwingUtilities, WindowConstants

HINT = u"wheel: zoom · drag: move · right click: fit"


class _G(object):
    """Graphics2D calls through the public interface (Java 17 module access from Jython)."""

    def __init__(self, g):
        self._g = g

    def __getattr__(self, name):
        m = getattr(Graphics2D, name)
        return lambda *a: m(self._g, *a)


class _Mouse(MouseAdapter):
    def __init__(self, zp):
        MouseAdapter.__init__(self)
        self.zp, self.last = zp, None

    def mouseWheelMoved(self, e):
        self.zp.wheel(e.getX(), e.getY(), e.getPreciseWheelRotation())

    def mousePressed(self, e):
        self.last = (e.getX(), e.getY()) if SwingUtilities.isLeftMouseButton(e) else None

    def mouseDragged(self, e):
        if self.last is not None:
            self.zp.drag(e.getX() - self.last[0], e.getY() - self.last[1])
            self.last = (e.getX(), e.getY())

    def mouseReleased(self, e):
        self.last = None

    def mouseClicked(self, e):
        if SwingUtilities.isRightMouseButton(e):
            self.zp.reset()


class ZoomPan(object):
    """View transform of a panel: zoom 1x (fit) ... max_scale, kept inside the panel."""

    def __init__(self, panel, max_scale=40.0, step=1.25):
        self.panel, self.max_scale, self.step = panel, max_scale, step
        self.at = AffineTransform()
        m = _Mouse(self)
        panel.addMouseListener(m)
        panel.addMouseMotionListener(m)
        panel.addMouseWheelListener(m)

    def scale(self):
        return self.at.getScaleX()

    def wheel(self, x, y, rotation):
        s = self.scale()
        new = min(self.max_scale, max(1.0, s * self.step ** (-rotation)))
        if new <= 1.0001:
            self.reset()
            return
        f = new / s
        t = AffineTransform()
        t.translate(x, y)
        t.scale(f, f)
        t.translate(-x, -y)
        self.at.preConcatenate(t)
        self._clamp()
        self.panel.repaint()

    def drag(self, dx, dy):
        if self.scale() <= 1.0001:
            return
        self.at.preConcatenate(AffineTransform.getTranslateInstance(dx, dy))
        self._clamp()
        self.panel.repaint()

    def _clamp(self):
        """Keep the zoomed panel area covering the panel (no empty border when dragging)."""
        s = self.scale()
        w, h = self.panel.getWidth(), self.panel.getHeight()
        tx = min(0.0, max(w - w * s, self.at.getTranslateX()))
        ty = min(0.0, max(h - h * s, self.at.getTranslateY()))
        self.at.setTransform(s, 0, 0, s, tx, ty)

    def reset(self):
        self.at = AffineTransform()
        self.panel.repaint()

    def to_view(self, x, y):
        """Panel point (mouse) -> unzoomed panel point (where it would be at zoom 1x)."""
        p = self.at.inverseTransform(Point2D.Double(x, y), None)
        return p.getX(), p.getY()

    def apply(self, g):
        _G(g).transform(self.at)

    def text(self):
        return u"%s \u00b7 zoom %.1fx" % (HINT, self.scale())


class ImageView(JPanel):
    """One image, fitted; zoom / pan; overlay(g, k) paints in image pixels (k = screen pixels per image pixel);
    on_click(ix, iy) gets image pixels."""

    def __init__(self, image, overlay=None, on_click=None, size=(900, 560)):
        JPanel.__init__(self)
        self.image, self.overlay, self.on_click = image, overlay, on_click
        self.setPreferredSize(Dimension(size[0], size[1]))
        self.setBackground(Color(40, 40, 40))
        self.zp = ZoomPan(self)
        view = self

        class Click(MouseAdapter):
            def mouseClicked(self, e):
                if SwingUtilities.isLeftMouseButton(e) and view.on_click is not None:
                    p = view.to_image(e.getX(), e.getY())
                    if p is not None:
                        view.on_click(p[0], p[1])
        self.addMouseListener(Click())

    def fit(self):
        iw, ih = self.image.getWidth(), self.image.getHeight()
        w, h = self.getWidth(), self.getHeight() - 18
        s = min(w / float(iw), h / float(ih))
        return s, (w - iw * s) / 2.0, (h - ih * s) / 2.0

    def to_image(self, x, y):
        if self.image is None:
            return None
        vx, vy = self.zp.to_view(x, y)
        s, ox, oy = self.fit()
        ix, iy = (vx - ox) / s, (vy - oy) / s
        if 0 <= ix < self.image.getWidth() and 0 <= iy < self.image.getHeight():
            return ix, iy
        return None

    def set_image(self, image):
        self.image = image
        self.zp.reset()

    def paintComponent(self, graphics):
        self.super__paintComponent(graphics)
        g = _G(graphics)
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR)
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        old = g.getTransform()
        if self.image is not None:
            s, ox, oy = self.fit()
            g.setClip(0, 0, self.getWidth(), self.getHeight() - 18)
            self.zp.apply(graphics)
            g.translate(ox, oy)
            g.scale(s, s)
            g.drawImage(self.image, 0, 0, None)
            if self.overlay is not None:
                self.overlay(graphics, s * self.zp.scale())
            g.setTransform(old)
            g.setClip(None)
        g.setColor(Color(220, 220, 220))
        g.setFont(Font(Font.SANS_SERIF, Font.PLAIN, 12))
        g.drawString(self.zp.text(), 6, self.getHeight() - 5)


def cross(graphics, x, y, r, colour, k, width=2.0):
    """A cross of radius r screen pixels at image point (x, y), line width in screen pixels (k = scale)."""
    g = _G(graphics)
    g.setColor(colour)
    g.setStroke(BasicStroke(float(width / k)))
    rr = r / k
    g.drawLine(int(round(x - rr)), int(round(y)), int(round(x + rr)), int(round(y)))
    g.drawLine(int(round(x)), int(round(y - rr)), int(round(x)), int(round(y + rr)))


def image_window(title, image, html, overlay=None, on_click=None, buttons=(), parent=None):
    """Window: text (html) on top, zoomable image, buttons [(label, fn(window), tooltip)].  Returns (frame, view)."""
    f = JFrame(title)
    f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
    root = JPanel(BorderLayout(4, 4))
    text = JEditorPane("text/html", "<html><body style='font-family:sans-serif;font-size:11pt'>%s</body></html>" % html)
    text.setEditable(False)
    sp = JScrollPane(text)
    sp.setPreferredSize(Dimension(900, 96))
    root.add(sp, BorderLayout.NORTH)
    view = ImageView(image, overlay, on_click)
    root.add(view, BorderLayout.CENTER)
    b = JPanel(FlowLayout(FlowLayout.RIGHT))
    for item in list(buttons) + [("Close", lambda w: w.dispose(), "Close this window.")]:
        label, fn, tip = item
        btn = JButton(label, actionPerformed=lambda e, fn=fn: fn(f))
        btn.setToolTipText(tip)
        b.add(btn)
    root.add(b, BorderLayout.SOUTH)
    f.setContentPane(root)
    f.pack()
    if parent is not None:
        f.setLocationRelativeTo(parent)
    f.setVisible(True)
    view.info = text
    return f, view


def copy_image(img):
    """Detached copy (camera frames may be reused by the capture thread)."""
    out = BufferedImage(img.getWidth(), img.getHeight(), BufferedImage.TYPE_INT_RGB)
    g = out.createGraphics()
    Graphics2D.drawImage(g, img, 0, 0, None)
    Graphics2D.dispose(g)
    return out
