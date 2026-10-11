// The first game every studio opens with. It is also the reference example
// the studio agent follows: Phaser from esm.sh, studio assets and sounds,
// touch controls, resize handling, and a saved best score.
export const STARTER_META = {
  id: 'star-catcher',
  name: 'Star Catcher',
  description: 'Catch falling stars, dodge the rocks. Uses the hero, star, and rock sprites if you make them.',
  controls: 'Move with the stick, arrow keys, or A/D. Tap or press Space to restart.',
}

export const STARTER_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Star Catcher</title>
<style>html,body{margin:0;height:100%;background:#0b1020;overflow:hidden;touch-action:none}</style>
</head>
<body>
<script type="module">
import Phaser from 'https://esm.sh/phaser@3.90.0'

studio.controls({ stick: true, buttons: ['Go'] })

function ensureTexture(scene, key, draw, size) {
  if (scene.textures.exists(key)) return
  const g = scene.make.graphics({ x: 0, y: 0 }, false)
  draw(g)
  g.generateTexture(key, size, size)
  g.destroy()
}

class Play extends Phaser.Scene {
  constructor() { super('play') }
  preload() { studio.preloadPhaser(this) }
  create() {
    ensureTexture(this, 'hero', (g) => { g.fillStyle(0x7cf29a); g.fillRoundedRect(0, 0, 44, 44, 12); g.fillStyle(0x0b1020); g.fillRect(12, 14, 6, 8); g.fillRect(26, 14, 6, 8) }, 44)
    ensureTexture(this, 'star', (g) => { g.fillStyle(0xffd84a); g.fillPoints(Array.from({ length: 10 }, (_, i) => { const r = i % 2 ? 7 : 16; const a = -Math.PI / 2 + i * Math.PI / 5; return new Phaser.Geom.Point(16 + Math.cos(a) * r, 16 + Math.sin(a) * r) }), true) }, 32)
    ensureTexture(this, 'rock', (g) => { g.fillStyle(0x8a8fa3); g.fillCircle(16, 16, 15); g.fillStyle(0x6b7086); g.fillCircle(11, 12, 4) }, 32)
    this.physics.resume()
    const { width, height } = this.scale
    this.stars = Array.from({ length: 60 }, () => this.add.circle(Math.random() * width, Math.random() * height, Math.random() * 1.6 + 0.4, 0xffffff, Math.random() * 0.6 + 0.2))
    this.player = this.physics.add.image(width / 2, height - 110, 'hero').setCollideWorldBounds(true)
    this.fit(this.player, 52)
    this.items = this.physics.add.group()
    this.score = 0
    this.lives = 3
    this.speed = 170
    this.over = false
    this.hud = this.add.text(18, 16, '', { fontFamily: 'system-ui, sans-serif', fontSize: '22px', color: '#ffffff' }).setDepth(10)
    this.physics.add.overlap(this.player, this.items, (_player, item) => this.collect(item))
    this.spawner = this.time.addEvent({ delay: 620, loop: true, callback: () => this.spawn() })
    this.scale.on('resize', this.onResize, this)
    this.events.once('shutdown', () => this.scale.off('resize', this.onResize, this))
    this.updateHud()
  }
  fit(sprite, size) {
    const scale = size / Math.max(sprite.width, sprite.height)
    sprite.setScale(scale)
    sprite.body.setSize(sprite.width * 0.8, sprite.height * 0.8)
  }
  onResize(size) {
    this.physics.world.setBounds(0, 0, size.width, size.height)
    this.player.y = size.height - 110
  }
  spawn() {
    const good = Math.random() < 0.66
    const item = this.items.create(Phaser.Math.Between(26, this.scale.width - 26), -24, good ? 'star' : 'rock')
    this.fit(item, good ? 30 : 38)
    item.good = good
    item.setVelocityY(this.speed + Math.random() * 130)
    if (!good) item.setAngularVelocity(Phaser.Math.Between(-140, 140))
    this.speed = Math.min(520, this.speed + 2.5)
  }
  collect(item) {
    if (this.over) return
    if (item.good) {
      this.score += 1
      studio.sound('coin', [null, null, 1675, null, 0.06, 0.24, 1, 1.82, null, null, 837, 0.06])
      this.tweens.add({ targets: this.player, scale: this.player.scale * 1.15, duration: 80, yoyo: true })
    } else {
      this.lives -= 1
      studio.sound('hit', [null, null, 90, null, 0.01, 0.12, 4, 2.2, null, null, null, null, null, 9, 50, 0.2])
      this.cameras.main.shake(160, 0.012)
    }
    item.destroy()
    this.updateHud()
    if (this.lives <= 0) this.gameOver()
  }
  updateHud() {
    this.hud.setText('Stars ' + this.score + '   Lives ' + this.lives)
  }
  update() {
    if (this.over) return
    const tilt = studio.input.tilt ? studio.input.tilt.x : 0
    this.player.setVelocityX(Math.max(-1, Math.min(1, studio.input.x + tilt)) * 440)
    for (const item of this.items.getChildren()) if (item.y > this.scale.height + 40) item.destroy()
    for (const dot of this.stars) { dot.y += 0.4 + dot.radius * 0.3; if (dot.y > this.scale.height) dot.y = 0 }
  }
  gameOver() {
    this.over = true
    this.spawner.remove()
    this.physics.pause()
    const best = Math.max(this.score, studio.load('best') || 0)
    studio.save('best', best)
    const { width, height } = this.scale
    this.add.rectangle(width / 2, height / 2, width, height, 0x000000, 0.55).setDepth(20)
    this.add.text(width / 2, height / 2 - 40, 'Game over', { fontFamily: 'system-ui, sans-serif', fontSize: '40px', fontStyle: 'bold', color: '#ffffff' }).setOrigin(0.5).setDepth(21)
    this.add.text(width / 2, height / 2 + 12, 'Score ' + this.score + '   Best ' + best, { fontFamily: 'system-ui, sans-serif', fontSize: '22px', color: '#ffd84a' }).setOrigin(0.5).setDepth(21)
    this.add.text(width / 2, height / 2 + 56, 'Tap or press Space to play again', { fontFamily: 'system-ui, sans-serif', fontSize: '18px', color: '#cfd6ff' }).setOrigin(0.5).setDepth(21)
    const restart = () => { off(); this.scene.restart() }
    const off = studio.onPress('a', restart)
    this.input.once('pointerdown', restart)
  }
}

new Phaser.Game({
  type: Phaser.AUTO,
  backgroundColor: '#0b1020',
  scale: { mode: Phaser.Scale.RESIZE, width: window.innerWidth, height: window.innerHeight },
  physics: { default: 'arcade' },
  scene: [Play],
})
</script>
</body>
</html>
`
