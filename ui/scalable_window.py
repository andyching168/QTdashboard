from PyQt6.QtWidgets import QMainWindow, QGraphicsScene, QGraphicsView, QGraphicsProxyWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QTransform


class ScalableWindow(QMainWindow):
    """
    可縮放的視窗包裝器 - 用於開發環境按比例縮放儀表板
    保持 1920x480 (4:1) 的比例，方便在電腦上預覽 8.8 吋螢幕效果
    視窗本身也鎖定 4:1 比例
    """
    
    ASPECT_RATIO = 1920 / 480  # 4:1
    
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self._resizing = False  # 防止遞迴
        
        self.setWindowTitle("儀表板 - 可縮放預覽（拖曳邊框調整大小）")
        self.setMinimumSize(480, 120)
        
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setStyleSheet("background: #0a0a0f;")
        
        self.proxy = QGraphicsProxyWidget()
        self.proxy.setWidget(dashboard)
        self.scene.addItem(self.proxy)
        
        self.setCentralWidget(self.view)
        
        initial_width = 960
        initial_height = int(initial_width / self.ASPECT_RATIO)
        self.resize(initial_width, initial_height)
        
        self._update_scale_info()
    
    def resizeEvent(self, event):
        if self._resizing:
            return
        
        self._resizing = True
        
        new_width = event.size().width()
        new_height = event.size().height()
        old_width = event.oldSize().width() if event.oldSize().width() > 0 else new_width
        old_height = event.oldSize().height() if event.oldSize().height() > 0 else new_height
        
        width_changed = abs(new_width - old_width)
        height_changed = abs(new_height - old_height)
        
        if width_changed >= height_changed:
            corrected_height = int(new_width / self.ASPECT_RATIO)
            corrected_width = new_width
        else:
            corrected_width = int(new_height * self.ASPECT_RATIO)
            corrected_height = new_height
        
        if corrected_width < 480:
            corrected_width = 480
            corrected_height = 120
        
        if corrected_width != new_width or corrected_height != new_height:
            self.resize(corrected_width, corrected_height)
        
        self._resizing = False
        
        super().resizeEvent(event)
        
        view_width = self.view.viewport().width()
        view_height = self.view.viewport().height()
        
        scale = view_width / 1920
        
        transform = QTransform()
        transform.scale(scale, scale)
        self.view.setTransform(transform)
        
        self.view.centerOn(self.proxy)
        
        self._update_scale_info()
    
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._force_update_scale)
    
    def _force_update_scale(self):
        view_width = self.view.viewport().width()
        view_height = self.view.viewport().height()
        
        if view_width <= 0 or view_height <= 0:
            return
        
        scale = view_width / 1920
        
        transform = QTransform()
        transform.scale(scale, scale)
        self.view.setTransform(transform)
        
        self.view.centerOn(self.proxy)
        
        self._update_scale_info()
    
    def _update_scale_info(self):
        view_width = self.view.viewport().width()
        scale = view_width / 1920 * 100
        
        actual_width_mm = view_width / 96 * 25.4
        equivalent_inches = actual_width_mm / 25.4
        
        title = f"儀表板預覽 - {scale:.0f}% ({view_width}x{self.view.viewport().height()}) ≈ {equivalent_inches:.1f}吋寬"
        self.setWindowTitle(title)
