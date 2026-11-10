import pygame
from random import randint

pygame.init()
# здесь определяются константы
# СОЗДАЕМ КЛАCCЫ


class Card:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 70, 100)
        self.color = (200, 200, 0)
        self.on = False

    def draw(self):
        pygame.draw.rect(win, self.color, self.rect)
        pygame.draw.rect(win, (0, 0, 250), self.rect, 8)
        if self.on:
            pygame.draw.circle(win, (150, 150, 150), self.rect.center, 10)

    def update(self):
        global points, is_click
        if self.rect.collidepoint(x_mouse, y_mouse) and bt_mouse[0] and is_click == 0:
            if self.on:
                self.color = (0, 250, 0)
                points += 1
            else:
                self.color = (250, 0, 0)
                points -= 1
            is_click = 10
        if is_click > 0:
            is_click -= 1
            print(is_click)


def show_points_bar():
    for i in range(points):
        pygame.draw.circle(win, (0, 250, 0), (64 + i * 10, 20), 6)
        pygame.draw.circle(win, (0, 0, 0), (64 + i * 10, 20), 6, 2)


# создание объектов
win = pygame.display.set_mode((480, 320))  # - создает экран
clock = pygame.time.Clock()  # -таймер, объект отвечает за кол. кадров в сек FPS
run = True

points = 5
is_click = 0

c1 = Card(40, 40)
c2 = Card(140, 40)
c3 = Card(240, 40)
c4 = Card(340, 40)
cards = [c1, c2, c3, c4]
tick = 0
################   главный цикл    ####################
while run:
    # задержка
    clock.tick(120)
    # цикл обработки событий
    for i in pygame.event.get():
        if i.type == pygame.QUIT:
            run = False

    x_mouse, y_mouse = pygame.mouse.get_pos()
    bt_mouse = pygame.mouse.get_pressed()

    # УПРАВЛЕНИЕ ОБЪЕКТАМИ
    if tick % 50 == 0:
        c1.on = False
        c1.color = (250, 250, 0)
        c2.on = False
        c2.color = (250, 250, 0)
        c3.on = False
        c3.color = (250, 250, 0)
        c4.on = False
        c4.color = (250, 250, 0)
        n = randint(0, 3)
        cards[n].on = True
    c1.update()
    c2.update()
    c3.update()
    c4.update()

    # ОТРИСВКА КАДРА
    win.fill((150, 150, 150))

    c1.draw()
    c2.draw()
    c3.draw()
    c4.draw()
    show_points_bar()

    tick += 1
    pygame.display.update()

#######################################################
